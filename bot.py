import discord
import json
import os
import asyncio
import aiohttp
import requests
import pytz
import time
from datetime import datetime
from dotenv import load_dotenv
from aiohttp import web
from discord.utils import format_dt

load_dotenv()
from discord.ext import commands, tasks
from discord.commands import slash_command, Option

# Skin cache for fake-equip command
SKIN_CACHE = []
CACHE_TIMESTAMP = 0
CACHE_DURATION = 3600

async def update_skin_cache():
    global SKIN_CACHE, CACHE_TIMESTAMP
    current_time = time.time()
    
    # Only update cache if it's expired
    if not SKIN_CACHE or (current_time - CACHE_TIMESTAMP) > CACHE_DURATION:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://fortnite-api.com/v2/cosmetics/br/search/all") as response:
                if response.status == 200:
                    data = await response.json()
                    SKIN_CACHE = [item["name"] for item in data["data"]]
                    CACHE_TIMESTAMP = current_time

async def get_skin_names(ctx: discord.AutocompleteContext):
    await update_skin_cache()
    return [skin for skin in SKIN_CACHE if ctx.value.lower() in skin.lower()][:25]

async def get_cosmetic_names(ctx: discord.AutocompleteContext):
    global SKIN_CACHE, CACHE_TIMESTAMP
    current_time = time.time()
    
    type_param = ctx.options.get('type')
    
    if not SKIN_CACHE or (current_time - CACHE_TIMESTAMP) > CACHE_DURATION:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://fortnite-api.com/v2/cosmetics") as response:
                if response.status == 200:
                    data = await response.json()
                    SKIN_CACHE = data["data"]["br"]  
                    CACHE_TIMESTAMP = current_time

    type_mapping = {
        "skin": "outfit",
        "dance": "emote",
        "backpack": "backpack", 
        "pickaxe": "pickaxe"
    }

    filtered_items = []
    search_value = ctx.value.lower()
    target_type = type_mapping.get(type_param, "")

    try:
        for item in SKIN_CACHE:
            if (item.get("type", {}).get("value") == target_type and 
                search_value in item.get("name", "").lower()):
                filtered_items.append(item["name"])
                if len(filtered_items) >= 25:  # Limit to 25 results
                    break
    except Exception as e:
        print(f"Error filtering items: {e}")
        return []

    return filtered_items

# UptimeRobot keep-alive server
async def handle_ping(request):
    return web.Response(text="Bot is alive!", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_get('/ping', handle_ping)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get('PORT') or os.environ.get('AIOHTTP_PORT') or 8080)
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Uptime server started on port {port}")

intents = discord.Intents.all()
bot = discord.Bot(intents=intents)

# Ensure env compatibility on Cybrancee (supports env.txt and multiple token keys)
if not os.getenv('DISCORD_TOKEN') and not os.getenv('TOKEN') and not os.getenv('BOT_TOKEN'):
    load_dotenv('env.txt')

TOKEN = os.getenv('DISCORD_TOKEN') or os.getenv('TOKEN') or os.getenv('BOT_TOKEN')

if not TOKEN:
    print("ERROR: Discord token not found in environment!")
    print("Set 'DISCORD_TOKEN' or 'TOKEN' in your Cybrancee Secrets (or env.txt).")
    raise SystemExit(1)

class MemoryDatabase:
    def __init__(self):
        self.data = {}

    async def get_user_data(self, user_id):
        return self.data.get(str(user_id))

    async def update_user_data(self, user_id, new_data):
        self.data[str(user_id)] = new_data

db = MemoryDatabase()

ld = "<a:ld:1408435516101234788>"
chk = "<a:chk:1408435545318621195>"
fail = "<:fail:1408435561689256056>"

NotLoggedIn = discord.Embed(title=f"{fail} Account Not Linked",description="You have **no accounts linked** with the bot, try `/login`",color=discord.Color.red())
CredentialsExpired = discord.Embed(title=f"{fail} Invalid Login", description="Your **login credentials have expired**, logout of your current account & login again to fix this issue.", color=discord.Color.red())
UnknownError = discord.Embed(title=f"{fail} Error",description="An **error occurred whilst attempting to complete this request**, try again. If this **issue persists contact support**.",color= discord.Color.red())

async def UpdateInfoAccount(user_id):
    user_data = await db.get_user_data(str(user_id))
    if not user_data:
        return False

    try:
        current_selected = user_data.get('selected', 0)
        current_account = user_data['accounts'][current_selected]
        device_id = current_account['DeviceID']
        account_id = current_account['AccountId']
        secret = current_account['Secret']

        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token',
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Authorization': 'basic M2Y2OWU1NmM3NjQ5NDkyYzhjYzI5ZjFhZjA4YThhMTI6YjUxZWU5Y2IxMjIzNGY1MGE2OWVmYTY3ZWY1MzgxMmU='
                },
                data={
                    'grant_type': 'device-auth',
                    'device_id': device_id,
                    'account_id': account_id,
                    'secret': secret
                }
            ) as response:
                if response.status == 200:
                    token_data = await response.json()
                    current_account['AccessToken'] = token_data['access_token']
                    await db.update_user_data(str(user_id), user_data)
                    return True
                else:
                    return False

    except Exception as e:
        return False

async def FetchAvatarUser(user_id):
    user_data = await db.get_user_data(str(user_id))
    if not user_data:
        return None

    selected = user_data.get('selected', 0)
    selected_account = user_data['accounts'][selected]

    token_ref = selected_account.get('AccessToken')
    if not token_ref:
        return None

    accountid = selected_account['AccountId']

    headers = {"Authorization": f"Bearer {token_ref}"}
    url = f"https://avatar-service-prod.identity.live.on.epicgames.com/v1/avatar/fortnite/ids?accountIds={accountid}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            data = await response.json()

            if data and isinstance(data, list):
                idavatar = data[0].get('avatarId', '').replace('ATHENACHARACTER:', '')
                return f"https://fortnite-api.com/images/cosmetics/br/{idavatar}/icon.png"

            return None

@bot.slash_command(name="login", description="Links your Epic Games Account with the bot")
async def login(ctx):
    user_data = await db.get_user_data(str(ctx.author.id))

    if user_data and user_data.get('accounts'):
        accounts = user_data['accounts']
        current_selected = user_data.get('selected', 0)

        class AccountButtons(discord.ui.View):
            def __init__(self, parent_ctx):
                super().__init__()
                self.parent_ctx = parent_ctx

            async def create_account_button(self, account, index):
                button = discord.ui.Button(
                    label=account['Display Name'],
                    style=discord.ButtonStyle.primary,
                    custom_id=f"account_{index}"
                )

                async def account_button_callback(interaction: discord.Interaction):
                    if interaction.user.id != self.parent_ctx.author.id:
                        await interaction.response.send_message("You cannot use these buttons.", ephemeral=True)
                        return

                    user_data['selected'] = index
                    await db.update_user_data(str(ctx.author.id), user_data)

                    avatar = await FetchAvatarUser(ctx.author.id)

                    embed = discord.Embed(
                        title=f"Switched Account {chk}",
                        description=f"**Display Name:** `{account['Display Name']}`\n**Account ID:** `{account['AccountId']}`",
                        color=discord.Color.green()
                    )

                    embed.set_thumbnail(url=avatar)
                    await interaction.response.edit_message(embed=embed, view=None)

                button.callback = account_button_callback
                return button

        view = AccountButtons(ctx)

        for i, account in enumerate(accounts):
            button = await view.create_account_button(account, i)
            view.add_item(button)

        add_account_button = discord.ui.Button(
            label="Add New Account", 
            style=discord.ButtonStyle.green,
            custom_id="add_account"
        )

        async def add_account_callback(interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("You cannot use these buttons.", ephemeral=True)
                return

            if len(accounts) >= 15:
                embed_error = discord.Embed(
                    title=f"Account Limit Reached",
                    description="You've reached the **maximum number** of accounts that can be linked (15).",
                    color=discord.Color.orange()
                )
                await interaction.message.edit(view=None)
                await interaction.response.send_message(embed=embed_error)
                return

            await interaction.message.edit(view=None)
            await interaction.response.defer()
            await start_login_process(interaction)

        add_account_button.callback = add_account_callback
        view.add_item(add_account_button)

        current_account = accounts[current_selected]
        embed = discord.Embed(
            title="Account Manager",
            description=f"**Current Account:** `{current_account['Display Name']}`\nSelect an account to switch to, or add a new one",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(
            url="https://images-ext-1.discordapp.net/external/F-LsmpDH5P80no0iCGe0R0ZgMlfoRuXiFXGuT5PEVVI/https/upload.wikimedia.org/wikipedia/commons/thumb/3/31/Epic_Games_logo.svg/1764px-Epic_Games_logo.svg.png?format=webp&quality=lossless&width=544&height=631"
        )

        await ctx.respond(embed=embed, view=view)
        return

    await start_login_process(ctx)

async def start_login_process(ctx_or_interaction):
    is_interaction = isinstance(ctx_or_interaction, discord.Interaction)

    try:
        async with aiohttp.ClientSession() as session:
            url = 'https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token'
            headers = {
                "Authorization": "Basic OThmN2U0MmMyZTNhNGY4NmE3NGViNDNmYmI0MWVkMzk6MGEyNDQ5YTItMDAxYS00NTFlLWFmZWMtM2U4MTI5MDFjNGQ3",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            data = {"grant_type": "client_credentials"}
            response = await session.post(url, data=data, headers=headers)
            response_data = await response.json()
            access_token = response_data['access_token']

            url = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/deviceAuthorization"
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            data = {'prompt': 'login'}
            response = await session.post(url, data=data, headers=headers)
            device_data = await response.json()
            verification_uri_complete = device_data['verification_uri_complete']
            device_code = device_data['device_code']

            embed = discord.Embed(
                title=f"Login Process {ld}",
                description=(
                    f"To login, follow these steps:\n\n"
                    f"1. **Open the Login Link:** [Login Link]({verification_uri_complete})\n"
                    f"2. **Confirm the request**\n"
                    f"3. **Wait a few seconds** for the connection to finish.\n\n"
                    "Once done, you will receive a confirmation message here!"
                ),
                color=discord.Color.gold()
            )
            embed.set_footer(text="This process won't take long.")
            embed.set_thumbnail(url="https://images-ext-1.discordapp.net/external/F-LsmpDH5P80no0iCGe0R0ZgMlfoRuXiFXGuT5PEVVI/https/upload.wikimedia.org/wikipedia/commons/thumb/3/31/Epic_Games_logo.svg/1764px-Epic_Games_logo.svg.png?format=webp&quality=lossless&width=544&height=631")

            if is_interaction:
                message = await ctx_or_interaction.original_response()
                await message.edit(embed=embed)
            else:
                await ctx_or_interaction.respond(embed=embed)

            ready = False
            while not ready:
                await asyncio.sleep(10)

                url = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token"
                headers = {
                    'Authorization': "Basic OThmN2U0MmMyZTNhNGY4NmE3NGViNDNmYmI0MWVkMzk6MGEyNDQ5YTItMDAxYS00NTFlLWFmZWMtM2U4MTI5MDFjNGQ3",
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
                data = {
                    'grant_type': 'device_code',
                    'device_code': device_code
                }
                response = await session.post(url, data=data, headers=headers)

                if response.status == 200:
                    ready = True
                    auth = await response.json()
                    access_token = auth['access_token']

                    url = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/exchange"
                    headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    }
                    response = await session.get(url, headers=headers)
                    if response.status == 200:
                        data = await response.json()
                        exchange_code = data['code']

                        url = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token"
                        grant_data = {
                            'grant_type': 'exchange_code',
                            'exchange_code': exchange_code
                        }
                        headers = {
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'Authorization': 'Basic M2Y2OWU1NmM3NjQ5NDkyYzhjYzI5ZjFhZjA4YThhMTI6YjUxZWU5Y2IxMjIzNGY1MGE2OWVmYTY3ZWY1MzgxMmU='
                        }
                        response = await session.post(url, data=grant_data, headers=headers)

                        if response.status == 200:
                            authentication = await response.json()
                            display_name = authentication['displayName']
                            account_id = authentication['account_id']
                            access_token = authentication['access_token']

                            url = f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}/deviceAuth"
                            headers2 = {
                                "Authorization": f"Bearer {access_token}",
                                "Content-Type": "application/json"
                            }
                            response = await session.post(url, headers=headers2)
                            if response.status == 200:
                                data = await response.json()
                                device_id = data['deviceId']
                                secret = data['secret']

                                account_data = {
                                    "Display Name": display_name,
                                    "AccountId": account_id,
                                    "DeviceID": device_id,
                                    "Secret": secret,
                                    "AccessToken": access_token
                                }

                                user_data = await db.get_user_data(ctx_or_interaction.user.id) or {"selected": 0, "accounts": []}

                                account_exists = any(acc.get('AccountId') == account_id for acc in user_data["accounts"])

                                if account_exists:
                                    embed = discord.Embed(
                                        title=f"Account Already Linked {fail}",
                                        description=f"The account **{display_name}** is already linked to the bot.",
                                        color=discord.Color.red()
                                    )
                                    if is_interaction:
                                        await message.edit(embed=embed)
                                    else:
                                        await ctx_or_interaction.respond(embed=embed)
                                    return

                                user_data["accounts"].append(account_data)
                                await db.update_user_data(ctx_or_interaction.user.id, user_data)

                                avatar = await FetchAvatarUser(ctx_or_interaction.user.id)

                                embed = discord.Embed(
                                    title=f"Login Successful {chk}",
                                    description=(
                                        f"**Display Name:** `{display_name}`\n"
                                        f"**Account ID:** `{account_id}`\n\n"
                                        "Your account has been successfully linked to the bot."
                                    ),
                                    color=discord.Color.green()
                                )
                                embed.set_thumbnail(url="https://images-ext-1.discordapp.net/external/F-LsmpDH5P80no0iCGe0R0ZgMlfoRuXiFXGuT5PEVVI/https/upload.wikimedia.org/wikipedia/commons/thumb/3/31/Epic_Games_logo.svg/1764px-Epic_Games_logo.svg.png?format=webp&quality=lossless&width=544&height=631")
                                if is_interaction:
                                    await message.edit(embed=embed)
                                else:
                                    await ctx_or_interaction.respond(embed=embed)
                            else:
                                raise Exception("Failed to fetch device details.")
                        else:
                            raise Exception("Failed to fetch exchange code.")
                    else:
                        raise Exception("Failed to fetch exchange code.")
                elif response.status == 400:
                    continue
                else:
                    raise Exception("Failed to fetch access token.")
    except Exception as e:
        embed_error = discord.Embed(
            title=f"Error {fail}",
            description=f"An error occurred during the login process:\n\n**Error:** `{str(e)}`",
            color=discord.Color.red()
        )
        embed_error.set_footer(text="Please try again later or contact support if the issue persists.")
        if is_interaction:
            await message.edit(embed=embed_error)
        else:
            await ctx_or_interaction.respond(embed=embed_error)

@bot.slash_command(description="Logs your linked account out of the bot")
async def logout(ctx):
    user_data = await db.get_user_data(ctx.author.id)

    if not user_data or not user_data.get('accounts'):
        await ctx.respond(embed=NotLoggedIn)
        return

    current_selected = user_data.get('selected', 0)
    accounts = user_data['accounts']

    current_account = accounts[current_selected]
    display_name = current_account['Display Name']
    avatar = await FetchAvatarUser(ctx.author.id)

    accounts.pop(current_selected)

    if accounts:
        user_data['accounts'] = accounts
        user_data['selected'] = min(current_selected, len(accounts)-1)
        await db.update_user_data(ctx.author.id, user_data)
    else:
        db.data.pop(str(ctx.author.id), None)

    embed = discord.Embed(
        title=f"{chk} Logout Successful",
        description=f"Your account **{display_name}** has been removed from our database!",
        colour=discord.Colour.green()
    )
    embed.set_thumbnail(url=avatar)
    await ctx.respond(embed=embed)

class Panel2(discord.ui.View):  
    def __init__(self, author_id):
        super().__init__(timeout=1500)
        self.author_id = author_id  

    @discord.ui.button(label="Timer", style=discord.ButtonStyle.primary)
    async def button_callback1(self, button, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:  
            embed = discord.Embed(description="You did not do this command!", color=discord.Color.brand_red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer()

        user_data = await db.get_user_data(interaction.user.id)

        if not user_data:
            await interaction.followup.send(embed=NotLoggedIn, ephemeral=True)
            return

        current_selected = user_data.get('selected', 0)
        accounts = user_data.get('accounts', [])

        if not accounts:
            await interaction.followup.send(embed=NotLoggedIn, ephemeral=True)
            return

        await UpdateInfoAccount(interaction.user.id)

        current_account = accounts[current_selected]
        access_token = current_account['AccessToken']
        account_id = current_account['AccountId']
        display_name = current_account['Display Name']
        avatar = await FetchAvatarUser(interaction.user.id)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }

        data = json.dumps({})
        message = None
        countdown_duration = None

        while True:
            req = requests.post(
                f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/QueryProfile?profileId=theater0&rvn=-1", 
                headers=headers, 
                data=data
            )

            if req.status_code == 200:
                res = req.json()
                profile_lock_info = res.get('profileChanges', [{}])[0].get('profile', {})
                profile_lock_expiration = profile_lock_info.get('profileLockExpiration', None)

                if profile_lock_expiration:
                    try:
                        if profile_lock_expiration.endswith('Z'):
                            profile_lock_expiration = profile_lock_expiration[:-1] + '+00:00'
                        expiration_time_utc = datetime.fromisoformat(profile_lock_expiration)
                        expiration_time_est = expiration_time_utc.astimezone(pytz.timezone('America/New_York'))

                        now = datetime.now(pytz.timezone('America/New_York'))
                        time_remaining = expiration_time_est - now

                        countdown_duration = max(0, int(time_remaining.total_seconds()))
                    except (ValueError, OverflowError):
                        countdown_duration = 0

                if countdown_duration == 0:
                    embed_error = discord.Embed(
                        description="Your profile is already **unlocked**. Click the **Start** button to enable the dupe!",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed_error, ephemeral=True)
                    return

                await UpdateInfoAccount(interaction.user.id)

                embed1 = discord.Embed(description=f"Waiting **{countdown_duration}** seconds before you can enable...", color=discord.Color.gold())
                embed1.set_author(name=display_name, icon_url=avatar)

                if not message:
                    await interaction.followup.send(embed=embed1)
                    message = await interaction.original_response()

                while countdown_duration > 0:
                    embed1.description = f"Waiting **{countdown_duration}** seconds before you can enable..."
                    await message.edit(embed=embed1)
                    await asyncio.sleep(1)
                    countdown_duration -= 1

                # Auto-enable the dupe after timer ends
                embed2 = discord.Embed(description="Your profile has **unlocked**! Auto-enabling dupe...", color=discord.Color.green())
                embed2.set_author(name=display_name, icon_url=avatar)
                await message.edit(embed=embed2, view=None)

                # Auto-enable dupe functionality
                g_chan = 1346259089508008057
                GLOBAL_CHANNEL = int(g_chan)
                global_crash = bot.get_channel(GLOBAL_CHANNEL)

                url = f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/user/{account_id}"
                response = requests.get(url, headers=headers)

                party = response.json().get('current', [])

                if not party:
                    embed_error = discord.Embed(description=f"{fail} Account is not in a homebase - cannot auto-enable dupe.", color=discord.Color.red())
                    embed_error.set_author(name=display_name, icon_url=avatar)
                    await interaction.followup.send(embed=embed_error)
                else:
                    await UpdateInfoAccount(interaction.user.id)

                    body2 = json.dumps({"primaryQuickbarChoices": ["", "", ""], "secondaryQuickbarChoice": ""})
                    url2 = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/ModifyQuickbar?profileId=theater0&rvn=-1"
                    response2 = requests.post(url2, headers=headers, data=body2)

                    if response2.status_code == 200:
                        enabled = discord.Embed(description=f'{chk} Dupe **auto-enabled** successfully! You can now **drop an item** & **pick it up** to **enable the dupe!**', color=discord.Color.green())
                        enabled.set_author(name=f"{display_name}", icon_url=avatar)
                        await interaction.followup.send(embed=enabled)

                        await asyncio.sleep(6)

                        if global_crash:
                            global_embed = discord.Embed(description=f"🌐 **Global Dupe Auto-Enable Detected!**\n> **User:** `{display_name}`", color=discord.Color.yellow())
                            global_embed.set_footer(text=f'{account_id}',icon_url=avatar)
                            await global_crash.send(embed=global_embed)
                    elif 'errors.com.epicgames.account.invalid_account_credentials' in str(response2.text):
                        await interaction.followup.send(embed=CredentialsExpired)
                    else:
                        failed = discord.Embed(description=f"{fail} Failed to auto-enable dupe on **{display_name}**!", color=discord.Color.red())
                        failed.set_author(name=f"{display_name}", icon_url=avatar)
                        await interaction.followup.send(embed=failed)

                break
            elif 'errors.com.epicgames.account.invalid_account_credentials' in str(req.text):
                await interaction.followup.send(embed=CredentialsExpired, ephemeral=True)
            elif req.status_code != 400:
                await interaction.followup.send(embed=UnknownError, ephemeral=True)
                break

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success)
    async def button_callback2(self, button, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:  
            embed = discord.Embed(description=f"You did not do this command!", color=discord.Color.brand_red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer()

        user_data = await db.get_user_data(interaction.user.id)

        if not user_data:
            await interaction.followup.send(embed=NotLoggedIn, ephemeral=True)
            return

        current_selected = user_data.get('selected', 0)
        accounts = user_data.get('accounts', [])

        if not accounts:
            await interaction.followup.send(embed=NotLoggedIn, ephemeral=True)
            return

        await UpdateInfoAccount(interaction.user.id)

        current_account = accounts[current_selected]
        access_token = current_account['AccessToken']
        account_id = current_account['AccountId']
        display_name = current_account['Display Name']
        avatar = await FetchAvatarUser(interaction.user.id)

        g_chan = 1346259089508008057
        GLOBAL_CHANNEL = int(g_chan)
        global_crash = bot.get_channel(GLOBAL_CHANNEL)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }

        url = f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/user/{account_id}"
        response = requests.get(url, headers=headers)

        party = response.json().get('current', [])

        if not party:
            embed = discord.Embed(description=f"{fail} Account is not in a homebase.", color=discord.Color.red())
            embed.set_author(name=f'{display_name}', icon_url=avatar)
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await UpdateInfoAccount(interaction.user.id)

            body2 = json.dumps({"primaryQuickbarChoices": ["", "", ""], "secondaryQuickbarChoice": ""})
            url2 = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/ModifyQuickbar?profileId=theater0&rvn=-1"
            response2 = requests.post(url2, headers=headers, data=body2)

            if response2.status_code == 200:
                enabled = discord.Embed(description=f'{chk} You can now **drop an item** & **pick it up** to **enable the dupe!**', color=discord.Color.green())
                enabled.set_author(name=f"{display_name}", icon_url=avatar)
                await interaction.followup.send(embed=enabled, view=None, ephemeral=False)

                await asyncio.sleep(6)

                if global_crash:
                    global_embed = discord.Embed(description=f"🌐 **Global Dupe Enable Detected!**\n> **User:** `{display_name}`", color=discord.Color.yellow())
                    global_embed.set_footer(text=f'{account_id}',icon_url=avatar)
                    await global_crash.send(embed=global_embed)
            elif 'errors.com.epicgames.account.invalid_account_credentials' in str(response2.text):
                await interaction.followup.send(embed=CredentialsExpired, ephemeral=True)
            elif response2.status_code != 400:
                failed = discord.Embed(description=f"{fail} Failed to enable dupe on **{display_name}**, if you need help join our support server & open a support ticket with context of your problem!", color=discord.Color.red())
                failed.set_author(name=f"{display_name}", icon_url=avatar)
                await interaction.followup.send(embed=failed, ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger)
    async def button_callback3(self, button, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:  
            embed = discord.Embed(description=f"You did not do this command!", color=discord.Color.brand_red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer()

        user_data = await db.get_user_data(interaction.user.id)

        if not user_data:
            await interaction.followup.send(embed=NotLoggedIn, ephemeral=True)
            return

        current_selected = user_data.get('selected', 0)
        accounts = user_data.get('accounts', [])

        if not accounts:
            await interaction.followup.send(embed=NotLoggedIn, ephemeral=True)
            return

        await UpdateInfoAccount(interaction.user.id)

        current_account = accounts[current_selected]
        access_token = current_account['AccessToken']
        account_id = current_account['AccountId']
        display_name = current_account['Display Name']
        avatar = await FetchAvatarUser(interaction.user.id)

        headers = {
            "Authorization": f"Bearer {access_token}"
        }

        url = f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/user/{account_id}"
        response = requests.get(url, headers=headers)

        party = response.json().get('current', [])

        if not party:
            embed = discord.Embed(description=f"{fail} Account not in a homebase.", color=discord.Color.red())
            embed.set_author(name=f'{display_name}', icon_url=avatar)
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            party_id = party[0]['id']

            url = f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/parties/{party_id}/members/{account_id}"
            response = requests.delete(url, headers=headers)

            left = discord.Embed(description=f"{chk} You have **successfully disabled** the dupe.", colour=discord.Colour.green())
            left.set_author(name=f"{display_name}", icon_url=avatar)
            await interaction.followup.send(embed=left, view=None, ephemeral=False)

@bot.slash_command(name="fake-equip", description="Allows you to visually equip any cosmetic")
@commands.cooldown(1, 5, commands.BucketType.user)
async def ghost_equip(
    ctx,
    type: Option(str, "Choose the type of item to equip", choices=["skin", "dance", "backpack", "pickaxe"]),
    name: Option(str, "Enter the name of the cosmetic", autocomplete=get_cosmetic_names)
):
    try:
        await ctx.defer()
        
        async with aiohttp.ClientSession() as session:

            user_data = await db.get_user_data(ctx.author.id)
            
            if not user_data:
                await ctx.respond(embed=NotLoggedIn)
                return

            current_selected = user_data.get('selected', 0)
            accounts = user_data['accounts']
            current_account = accounts[current_selected]
            
            await UpdateInfoAccount(ctx.author.id)

            access_token = current_account['AccessToken']
            account_id = current_account['AccountId']
            display_name = current_account['Display Name']
            avatar = await FetchAvatarUser(ctx.author.id)

            type_mapping = {
                "skin": "outfit",
                "dance": "emote", 
                "backpack": "backpack",
                "pickaxe": "pickaxe"
            }

            search_url = f'https://fortnite-api.com/v2/cosmetics/br/search?name={name}&type={type_mapping[type]}'
            async with session.get(search_url, timeout=30) as search_response:
                if search_response.status != 200:
                    embed = discord.Embed(
                        title=f"{fail} Item Not Found",
                        description=f'The {type} **{name}** does not exist.',
                        color=discord.Color.red()
                    )
                    embed.set_thumbnail(url=avatar)
                    await ctx.respond(embed=embed, ephemeral=True)
                    return

                cosmetic_data = await search_response.json()
                cosmetic_id = cosmetic_data['data']['id']
                cosmetic_name = cosmetic_data['data']['name']
                image_url = cosmetic_data['data']['images']['icon']
                variants = cosmetic_data['data'].get('variants', [])[:5]

                g_chan = 1346259089508008057
                GLOBAL_CHANNEL = int(g_chan)
                global_crash = bot.get_channel(GLOBAL_CHANNEL)

                party_url = f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/user/{account_id}"
                headers = {"Authorization": f"Bearer {access_token}"}

                async with session.get(party_url, headers=headers, timeout=30) as party_response:
                    party_data = await party_response.json()
                    
                    if not party_data.get('current'):
                        embed = discord.Embed(
                            title="⚠️ Not in Party",
                            description="You must be in a party to use this command.",
                            color=discord.Color.red()
                        )
                        embed.set_thumbnail(url=avatar)
                        await ctx.respond(embed=embed, ephemeral=True)
                    elif 'errors.com.epicgames.account.invalid_account_credentials' in str(party_response.text):
                        await ctx.respond(embed=CredentialsExpired, ephemeral=True)
                        return

                    current_parties = party_data.get('current', [])
                    if not current_parties:
                        embed = discord.Embed(
                            title="⚠️ Not in Party",
                            description="You must be in a party to use this command.",
                            color=discord.Color.red()
                        )
                        embed.set_thumbnail(url=avatar)
                        await ctx.respond(embed=embed, ephemeral=True)
                        return
                        
                    party_id = current_parties[0]['id']
                    
                    variantmeta = '{"AthenaCosmeticLoadoutVariants": {"vL": {}}}'
                    loadoutmeta = '{"AthenaCosmeticLoadout": {}}'
                    revision = 0
                    
                    for member in current_parties[0]['members']:
                        if member['account_id'] == account_id:
                            variantmeta = member['meta'].get('Default:AthenaCosmeticLoadoutVariants_j', '{"AthenaCosmeticLoadoutVariants": {"vL": {}}}')
                            loadoutmeta = member['meta'].get('Default:AthenaCosmeticLoadout_j', '{"AthenaCosmeticLoadout": {}}')
                            revision = member['revision']
                            break

                    class StyleSelect(discord.ui.Select):
                        def __init__(self, variant):
                            options = [
                                discord.SelectOption(
                                    label=f"{option['name']}",
                                    description=f"Style for {variant['channel']}",
                                    value=f"{variant['channel']}:{option['tag']}"
                                ) for option in variant['options']
                            ]
                            
                            super().__init__(
                                placeholder=f"Select {variant['channel']} style...",
                                min_values=1,
                                max_values=1,
                                options=options,
                                custom_id=variant['channel']
                            )

                    class StyleView(discord.ui.View):
                        def __init__(self, variants):
                            super().__init__()
                            self.selected_styles = {}
                            
                            for variant in variants:
                                self.add_item(StyleSelect(variant))

                        @discord.ui.button(label="Confirm Equip", style=discord.ButtonStyle.primary)
                        async def ghost_equip(self, button: discord.ui.Button, interaction: discord.Interaction):
                            if interaction.user.id != ctx.author.id:
                                await interaction.response.send_message("You cannot use this menu.", ephemeral=True)
                                return

                            cosmetic_mapping = {
                                "skin": {"characterPrimaryAssetId": f"AthenaCharacter:{cosmetic_id}"},
                                "dance": {"emoteItemDef": f"/BRCosmetics/Athena/Items/Cosmetics/Dances/{cosmetic_id}.{cosmetic_id}", "emoteEKey": "", "emoteSection": -2, "multipurposeEmoteData": -1},
                                "backpack": {"backpackDef": f"/BRCosmetics/Athena/Items/Cosmetics/Backpacks/{cosmetic_id}.{cosmetic_id}", "backpackEKey": ""},
                                "pickaxe": {"pickaxeDef": f"/BRCosmetics/Athena/Items/Cosmetics/Pickaxes/{cosmetic_id}.{cosmetic_id}", "pickaxeEKey": ""}
                            }

                            loadout_data = {
                                "Default:AthenaCosmeticLoadout_j": json.dumps({
                                    "AthenaCosmeticLoadout": cosmetic_mapping[type]
                                })
                            }

                            if type == "dance":
                                loadout_data["Default:FrontendEmote_j"] = json.dumps({
                                    "FrontendEmote": cosmetic_mapping[type]
                                })

                            if self.selected_styles:
                                variant_data = json.loads(variantmeta)
                                vl = variant_data["AthenaCosmeticLoadoutVariants"]["vL"]
                                variant_list = []
                                
                                for channel, tag in self.selected_styles.items():
                                    variant_list.append({"c": channel, "v": tag, "dE": 0})
                                
                                if variant_list:
                                    type_mapping = {
                                        "skin": "AthenaCharacter",
                                        "backpack": "AthenaBackpack",
                                        "pickaxe": "AthenaPickaxe"
                                    }
                                    vl[type_mapping.get(type, type)] = {"i": variant_list}
                                    variant_data["AthenaCosmeticLoadoutVariants"]["vL"] = vl
                                    loadout_data["Default:AthenaCosmeticLoadoutVariants_j"] = json.dumps(variant_data)

                            patch_url = f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/parties/{party_id}/members/{account_id}/meta"
                            body = {
                                'delete': [],
                                'revision': revision,
                                'update': loadout_data
                            }

                            async with aiohttp.ClientSession() as session:
                                headers = {"Authorization": f"Bearer {access_token}"}
                                async with session.patch(patch_url, headers=headers, json=body, timeout=30) as patch_response:
                                    styles_text = "\n".join([f"• {channel}: {tag}" for channel, tag in self.selected_styles.items()])
                                    embed = discord.Embed(
                                        description=f'{chk} Successfully equipped **{cosmetic_name}**\n\nSelected Styles:\n{styles_text if styles_text else "Default"}\n\n**(Cosmetics not shown to you)**\nShown to Party Members Only',
                                        color=discord.Color.green()
                                    )
                                    embed.set_author(name=f"{display_name}", icon_url=avatar)
                                    embed.set_thumbnail(url=image_url)
                                    await interaction.response.edit_message(embed=embed, view=None)

                                    if global_crash:
                                        await asyncio.sleep(7)
                                        global_embed = discord.Embed(description=f"🌐 **Global Ghost Equip Detected!**\n> **User:** `{display_name}`", color=discord.Color.yellow())
                                        global_embed.set_footer(text=f'{account_id}',icon_url=avatar)
                                        await global_crash.send(embed=global_embed)

                        async def interaction_check(self, interaction: discord.Interaction) -> bool:
                            if isinstance(interaction.data, dict):
                                custom_id = interaction.data.get("custom_id", "")
                                values = interaction.data.get("values", [])
                                if values and custom_id:
                                    channel = custom_id
                                    selected_value = values[0]
                                    self.selected_styles[channel] = selected_value.split(":")[1]
                                    await interaction.response.defer()
                                    return True
                            return True

                    if variants:
                        initial_embed = discord.Embed(
                            title="Select Style Variants",
                            description=f"Choose style variants for **{cosmetic_name}**\nThen click 'Confirm Equip' to apply",
                            color=discord.Color.blue()
                        )
                        initial_embed.set_thumbnail(url=image_url)
                        await ctx.respond(embed=initial_embed, view=StyleView(variants))
                    else:
                        cosmetic_mapping = {
                            "skin": {"characterPrimaryAssetId": f"AthenaCharacter:{cosmetic_id}"},
                            "dance": {"emoteItemDef": f"/BRCosmetics/Athena/Items/Cosmetics/Dances/{cosmetic_id}.{cosmetic_id}", "emoteEKey": "", "emoteSection": -2, "multipurposeEmoteData": -1},
                            "backpack": {"backpackDef": f"{cosmetic_id}"},
                            "pickaxe": {"pickaxeDef": f"/BRCosmetics/Athena/Items/Cosmetics/Pickaxes/{cosmetic_id}.{cosmetic_id}", "pickaxeEKey": ""}
                        }

                        loadout_data = {
                            "Default:AthenaCosmeticLoadout_j": json.dumps({
                                "AthenaCosmeticLoadout": cosmetic_mapping[type]
                            })
                        }

                        if type == "dance":
                            loadout_data["Default:FrontendEmote_j"] = json.dumps({
                                "FrontendEmote": cosmetic_mapping[type]
                            })

                        patch_url = f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/parties/{party_id}/members/{account_id}/meta"
                        body = {
                            'delete': [],
                            'revision': revision,
                            'update': loadout_data
                        }

                        pickaxeEmote = {
                            "Default:FrontendEmote_j": json.dumps({
                                "FrontendEmote": {
                                    "emoteItemDef": "/BRCosmetics/Athena/Items/Cosmetics/Dances/EID_IceKing.EID_IceKing",
                                    "emoteEKey": "",
                                    "emoteSection": -2, 
                                    "multipurposeEmoteData": -1
                                }
                            })
                        }

                        pickaxebody = {
                            'delete': [],
                            'revision': revision + 1,
                            'update': pickaxeEmote
                        }

                        embed = discord.Embed(
                            description=f'{chk} Successfully equipped **{cosmetic_name}**\n\n**(Cosmetics not shown to you)**\nShown to Party Members Only',
                            color=discord.Color.green()
                        )
                        embed.set_author(name=f"{display_name}", icon_url=avatar)
                        embed.set_thumbnail(url=image_url)

                        async with session.patch(patch_url, headers=headers, json=body, timeout=30) as patch_response:
                            if type == "pickaxe":
                                async with session.patch(patch_url, headers=headers, json=pickaxebody, timeout=30) as pickaxe_response:
                                    await ctx.respond(embed=embed)
                            else:
                                await ctx.respond(embed=embed)

                            if global_crash:
                                await asyncio.sleep(6)
                                global_embed = discord.Embed(description=f"🌐 **Global Ghost Equip Detected!**\n> **User:** `{display_name}`", color=discord.Color.yellow())
                                global_embed.set_footer(text=f'{account_id}',icon_url=avatar)
                                await global_crash.send(embed=global_embed)

    except Exception as e:
        error_embed = discord.Embed(
            title=f"{fail} Error",
            description=f"An error occurred while processing your request: {str(e)}",
            color=discord.Color.red()
        )
        try:
            await ctx.respond(embed=error_embed, ephemeral=True)
        except:
            await ctx.followup.send(embed=error_embed, ephemeral=True)
        print(f"Error in ghost_equip: {str(e)}")

@bot.slash_command(name="epic-services", description="Displays all Epic Server Statuses")
@commands.cooldown(1, 5, commands.BucketType.user)
async def epic_games_services(ctx):
    await ctx.defer()

    url = "https://status.epicgames.com/api/v2/summary.json"

    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()

            fortnite_components = {
                "Website": None,
                "Login": None,
                "Matchmaking": None,
                "Sessions": None,
                "Game Services": None,
                "Voice Chat": None,
                "Parties, Friends, and Messaging": None,
                "Stats and Leaderboards": None,
                "Item Shop": None,
                "Stats": None,
                "Fortnite Crew": None
            }

            services_down = False

            for component in data.get("components", []):
                name = component["name"]
                status = component["status"].capitalize()

                if name in fortnite_components and fortnite_components[name] is None:
                    fortnite_components[name] = status
                    if status != "Operational":
                        services_down = True 

            embed_color = discord.Color.green() if not services_down else discord.Color.red()

            embed = discord.Embed(
                title="Fortnite Status",
                color=embed_color,
            )

            for service, status in fortnite_components.items():
                if status:
                    status_emoji = f"{chk}" if status == "Operational" else f"{fail}"
                    embed.add_field(
                        name=service,
                        value=f"{status_emoji} {status}",
                        inline=True
                    )

            updated_at_utc = datetime.strptime(data['page']['updated_at'], "%Y-%m-%dT%H:%M:%S.%fZ")
            est = pytz.timezone("America/New_York")
            updated_at_est = updated_at_utc.astimezone(est)

            formatted_date = updated_at_est.strftime("%B %d, %Y - %I:%M %p EST")

            embed.set_footer(
                text=f"Last Updated: {formatted_date}"
            )

            embed.set_thumbnail(url="https://images-ext-1.discordapp.net/external/F-LsmpDH5P80no0iCGe0R0ZgMlfoRuXiFXGuT5PEVVI/https/upload.wikimedia.org/wikipedia/commons/thumb/3/31/Epic_Games_logo.svg/1764px-Epic_Games_logo.svg.png?format=webp&quality=lossless&width=544&height=631")

            embed.add_field(
                name="More Info",
                value="[Click me for more info](https://status.epicgames.com)",
                inline=False
            )
            
            await ctx.respond(embed=embed)

        else:
            await ctx.respond(f"Failed to retrieve status. Status code: {response.status_code}")

    except Exception as e:
        await ctx.respond(f"Error fetching Epic Games status: {e}")

class ConfirmButton(discord.ui.View):
    def __init__(self, user_id, action):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.action = action

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.primary)
    async def continue_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if self.action == "bp-destroy-all":
            await bpdestroyall(interaction)
        elif self.action == "st-destroy-all":
            await stdestroyall(interaction)

async def bpdestroyall(interaction):
    user_id = interaction.user.id

    user_data = await db.get_user_data(user_id)

    if not user_data or not user_data.get('accounts'):
        await interaction.followup.send(embed=NotLoggedIn, ephemeral=True)
        return

    current_selected = user_data.get('selected', 0)
    accounts = user_data['accounts']

    if not accounts:
        await interaction.followup.send(embed=NotLoggedIn, ephemeral=True)
        return

    await UpdateInfoAccount(user_id)

    current_account = accounts[current_selected]
    access_token = current_account['AccessToken']
    account_id = current_account['AccountId']
    display_name = current_account['Display Name']
    avatar = await FetchAvatarUser(user_id)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Query the profile for items
    profile_url = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/QueryProfile?profileId=theater0"
    prof_data = requests.post(profile_url, headers=headers, json={})

    if 'errors.com.epicgames.account.invalid_account_credentials' in str(prof_data.text):
        await interaction.followup.send(embed=CredentialsExpired, ephemeral=True)
        return

    if prof_data.status_code != 200:
        await interaction.followup.send(embed=discord.Embed(description="Failed to retrieve inventory data.", color=discord.Color.red()), ephemeral=True)
        return

    data = prof_data.json()
    item_types = {'Trap:': 'Traps', 'Ingredient:': 'Materials', 'Weapon:wid': 'Weapons/Melees', 'Ammo:': 'Ammo', 'WorldItem:': 'Building Mats'}
    item_groups = {k: [] for k in item_types}  # Stores items by type

    # List of templateIds to skip
    skip_template_ids = {
        "Weapon:buildingitemdata_floor",
        "Weapon:buildingitemdata_stair_w",
        "Weapon:buildingitemdata_roofs",
        "Weapon:buildingitemdata_wall"
    }

    # Group items by type
    for key, value in data["profileChanges"][0]["profile"]["items"].items():
        template_id = value.get('templateId', '')

        # Skip if template_id matches any in the list
        if template_id in skip_template_ids:
            continue  # Skip this item

        for item_type in item_groups:
            if template_id.startswith(item_type):
                item_groups[item_type].append(key)

    # Count items to destroy
    total_items = sum(len(ids) for ids in item_groups.values())

    if total_items == 0:
        await interaction.followup.send(embed=discord.Embed(description=f"{fail} No items found to destroy.", color=discord.Color.red()), ephemeral=True)
        return

    # Destroy items per type and track results
    destroy_url = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/DestroyWorldItems?profileId=theater0"
    results = {}

    for item_type, item_ids in item_groups.items():
        if item_ids:  # Only send request if items exist
            des_payload = json.dumps({"itemIds": item_ids})
            destroy_req = requests.post(destroy_url, headers=headers, data=des_payload)

            if destroy_req.status_code == 200:
                results[item_types[item_type]] = f"{chk} Destroyed"
            else:
                results[item_types[item_type]] = f"{fail} Failed to Destroy"
        else:
            results[item_types[item_type]] = f"{fail} Not Found"

    # Format results in embed message
    embed_description = "\n".join([f"> **{name}:** {status}" for name, status in results.items()])
    embed = discord.Embed(
        title="Destruction Summary",
        description=f"**Inventory Type:** `Backpack`\n{embed_description}",
        color=discord.Color.green()
    )

    await interaction.followup.send(embed=embed, view=None)

async def stdestroyall(interaction):
    user_id = interaction.user.id

    user_data = await db.get_user_data(user_id)

    if not user_data or not user_data.get('accounts'):
        await interaction.followup.send(embed=NotLoggedIn, ephemeral=True)
        return

    current_selected = user_data.get('selected', 0)
    accounts = user_data['accounts']

    if not accounts:
        await interaction.followup.send(embed=NotLoggedIn, ephemeral=True)
        return

    await UpdateInfoAccount(user_id)

    current_account = accounts[current_selected]
    access_token = current_account['AccessToken']
    account_id = current_account['AccountId']
    display_name = current_account['Display Name']
    avatar = await FetchAvatarUser(user_id)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Query the profile for items
    profile_url = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/QueryProfile?profileId=outpost0"
    prof_data = requests.post(profile_url, headers=headers, json={})

    if 'errors.com.epicgames.account.invalid_account_credentials' in str(prof_data.text):
        await interaction.followup.send(embed=CredentialsExpired, ephemeral=True)
        return

    if prof_data.status_code != 200:
        await interaction.followup.send(embed=discord.Embed(description="Failed to retrieve inventory data.", color=discord.Color.red()), ephemeral=True)
        return

    data = prof_data.json()
    item_types = {'Trap:': 'Traps', 'Ingredient:': 'Materials', 'Weapon:': 'Weapons/Melees', 'Ammo:': 'Ammo', 'WorldItem:': 'Building Mats'}
    item_groups = {k: [] for k in item_types}  # Stores items by type

    # Group items by type
    for key, value in data["profileChanges"][0]["profile"]["items"].items():
        template_id = value.get('templateId', '')
        if not template_id:
            continue  # Skip items with no templateId

        for item_type in item_groups:
            if template_id.startswith(item_type):
                item_groups[item_type].append(key)

    # Count items to destroy
    total_items = sum(len(ids) for ids in item_groups.values())

    if total_items == 0:
        await interaction.followup.send(embed=discord.Embed(description=f"{fail} No items found to destroy.", color=discord.Color.red()), ephemeral=True)
        return

    # Destroy items per type and track results
    destroy_url = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/DestroyWorldItems?profileId=outpost0"
    results = {}

    for item_type, item_ids in item_groups.items():
        if item_ids:  # Only send request if items exist
            des_payload = json.dumps({"itemIds": item_ids})
            destroy_req = requests.post(destroy_url, headers=headers, data=des_payload)

            if destroy_req.status_code == 200:
                results[item_types[item_type]] = f"{chk} Destroyed!"
            else:
                results[item_types[item_type]] = f"{fail} Failed to Destroy"
        else:
            results[item_types[item_type]] = f"{fail} Not Found"

    # Format results in embed message
    embed_description = "\n".join([f"> **{name}:** {status}" for name, status in results.items()])
    embed = discord.Embed(
        title="Destruction Summary",
        description=f"**Inventory Type:** `Storage`\n{embed_description}",
        color=discord.Color.green()
    )

    await interaction.followup.send(embed=embed, view=None)

@bot.slash_command(name="bp-destroy-all", description="Destroys all items within your backpack in Save the World")
async def bpdestroy(ctx: discord.ApplicationContext):
    await ctx.defer(ephemeral=True)
    
    embed = discord.Embed(
        title="⚠️ Warning!",
        description="This action will destroy all items within your backpack & cannot be undone.",
        color=discord.Color.red()
    )
    await ctx.respond(embed=embed, view=ConfirmButton(ctx.author.id, "bp-destroy-all"))

@bot.slash_command(name="st-destroy-all", description="Destroys all items within your storage in Save the World")
async def stdestroy(ctx: discord.ApplicationContext):
    await ctx.defer(ephemeral=True)
    
    embed = discord.Embed(
        title="⚠️ Warning!",
        description="This action will destroy all items within your storage & cannot be undone.",
        color=discord.Color.red()
    )
    await ctx.respond(embed=embed, view=ConfirmButton(ctx.author.id, "st-destroy-all"))

class Panel6(discord.ui.View):  
    def __init__(self, author_id):
        super().__init__(timeout=30)
        self.author_id = author_id 

    @discord.ui.button(label="SHOW", style=discord.ButtonStyle.danger)
    async def button_callback(self, button, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            embed = discord.Embed(description="You did not do this command!", color=discord.Color.brand_red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        success = await UpdateInfoAccount(interaction.user.id)
        if not success:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Error",
                    description="Failed to refresh account token. Please try logging in again.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return

        user_data = await db.get_user_data(interaction.user.id)
        print(user_data)
        
        if not user_data:
            await interaction.response.send_message(embed=NotLoggedIn, ephemeral=True)
            return

        current_selected = user_data.get('selected', 0)
        accounts = user_data.get('accounts', [])
        
        if not accounts:
            await interaction.response.send_message(embed=NotLoggedIn, ephemeral=True)
            return

        await UpdateInfoAccount(interaction.user.id)

        current_account = accounts[current_selected]
        access_token = current_account['AccessToken']
        account_id = current_account['AccountId']
        display_name = current_account['Display Name']
        device_id = current_account['DeviceID']
        secret = current_account['Secret']
        avatar = await FetchAvatarUser(interaction.user.id)

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        try:
            allinfo = requests.get(f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}", headers=headers)
            res = allinfo.json()

            if allinfo.status_code == 200:
                email = res.get('email', 'N/A')
                phone = res.get('phoneNumber', 'N/A')
                updisplay = res.get('canUpdateDisplayName', 'N/A')
                faenabled = res.get('tfaEnabled', 'N/A')
                verifiedemail = res.get('emailVerified', 'N/A')

                infoembed = discord.Embed(
                    title="Account Info",
                    description=(
                        f"**Basic Information**\n\n"
                        f"**Display:** `{display_name}`\n"
                        f"**Email:** ||`{email}`||\n"
                        f"**Account ID:** `{account_id}`\n"
                        f"**Device ID:** ||`{device_id}`||\n"
                        f"**Secret:** ||`{secret}`||\n\n"
                        f"**Other Information:**\n\n"
                        f"**Phone #:** ||`{phone}`||\n"
                        f"**Can Update Display:** `{updisplay}`\n"
                        f"**2FA Enabled:** `{faenabled}`\n"
                        f"**Email Verified:** `{verifiedemail}`"
                    ),
                    color=discord.Color.gold()
                )
                infoembed.set_thumbnail(url=avatar)
                await interaction.response.send_message(embed=infoembed, ephemeral=True)

            else:
                await interaction.response.send_message(embed=UnknownError, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(embed=UnknownError)
            print(e)

@bot.slash_command(name="account-info", description="Displays private information about your account")
@commands.cooldown(1, 5, commands.BucketType.user)
async def account_info(ctx):
    await ctx.defer(ephemeral=True)
    
    user_data = await db.get_user_data(ctx.author.id)
    
    if not user_data:
        await ctx.respond(embed=NotLoggedIn, ephemeral=True)
        return

    current_selected = user_data.get('selected', 0)
    accounts = user_data.get('accounts', [])
    
    if not accounts:
        await ctx.respond(embed=NotLoggedIn, ephemeral=True)
        return
    
    await UpdateInfoAccount(ctx.author.id)
    
    current_account = accounts[current_selected]
    access_token = current_account['AccessToken']
    account_id = current_account['AccountId']
    display_name = current_account['Display Name']
    avatar = await FetchAvatarUser(ctx.author.id)

    psn = "<:psn:1353584316092907521>"
    xbox = "<:xbox:1353584290998517800>"
    google = "<:google:1353584443842887780>"
    twitch = "<:twitch:1353584302591311925>"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        account_url = f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}"
        account_response = requests.get(account_url, headers=headers)
        
        if 'errors.com.epicgames.account.invalid_account_credentials' in str(account_response.text):
            await ctx.respond(embed=CredentialsExpired, ephemeral=True)
            return
            
        if account_response.status_code != 200:
            await ctx.respond(embed=discord.Embed(
                title=f"Error {fail}",
                description="Failed to retrieve account information.",
                color=discord.Color.red()
            ), ephemeral=True)
            return
            
        account_data = account_response.json()

        externals_url = f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}/externalAuths"
        externals_response = requests.get(externals_url, headers=headers)
        externals_data = externals_response.json() if externals_response.status_code == 200 else []
        
        match_url = f"https://fngw-mcp-gc-livefn.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/QueryProfile?profileId=athena&rvn=-1"
        match_response = requests.post(match_url, headers=headers, json={})
        match_data = match_response.json() if match_response.status_code == 200 else {}
        
        last_match = None
        
        if match_data and 'profileChanges' in match_data and match_data['profileChanges']:
            stats = match_data['profileChanges'][0]['profile'].get('stats', {}).get('attributes', {})
            if 'last_match_end_datetime' in stats:
                last_match_time = stats['last_match_end_datetime']
                try:
                    last_match_timestamp = datetime.fromisoformat(last_match_time.replace('Z', '+00:00'))
                    last_match = f"<t:{int(last_match_timestamp.timestamp())}:R>"
                except Exception:
                    last_match = last_match_time
        
        external_list = []
        for external in externals_data:
            auth_type = external.get('type', 'N/A')
            display_name = external.get('externalDisplayName', 'N/A')
            if display_name:
                external_list.append(f"{auth_type.lower()}: {display_name}")
            else:
                external_list.append(f"{auth_type.lower()}")
        
        if account_data.get('id'):
            external_list.insert(0, f"{account_data.get('id')}")
        
        embed = discord.Embed(color=discord.Color.yellow())
        embed.set_author(name=f"{account_data.get('displayName', 'N/A')}")
        
        account_section = (
            f"> **Verified Email:** {f'{chk}' if account_data.get('emailVerified', False) else f'{fail}'}\n"
            f"> **Last Match Played:** {last_match or 'Unknown'}\n"
            f"> **Account ID:** `{account_id}`"
        )
        embed.add_field(name="Account:", value=account_section, inline=False)
        
        externals_formatted = []
        for ext in external_list:
            if ":" in ext:
                platform, name = ext.split(":", 1)
                if platform.lower() == "twitch":
                    externals_formatted.append(f"{twitch} `{name.strip()}`")
                elif platform.lower() == "psn":
                    externals_formatted.append(f"{psn} `{name.strip()}`")
                elif platform.lower() == "google":
                    externals_formatted.append(f"{google} `{name.strip()}`")
                elif platform.lower() == "xbl":
                    externals_formatted.append(f"{xbox} `{name.strip()}`")
                else:
                    externals_formatted.append(f"{name.strip()}")
        
        externals_section = "\n".join([f"> {ext}" for ext in externals_formatted])
        embed.add_field(name="Account Externals:", value=externals_section, inline=False)
        
        name_value = account_data.get('name', 'N/A')
        email_value = account_data.get('email', 'N/A')
        check_mark = f"{chk}" if account_data.get('emailVerified', False) else f"{fail}"
        
        embed.add_field(name="Name:", value=f"> {name_value}", inline=True)
        embed.add_field(name="Email:", value=f"> {email_value} {check_mark}", inline=True)
        
        last_name_change_timestamp = None
        if account_data.get('lastDisplayNameChange'):
            last_name_change = datetime.fromisoformat(account_data.get('lastDisplayNameChange').replace('Z', '+00:00'))
            last_name_change_timestamp = int(last_name_change.timestamp())
        
        display_name_current = (
            f"> **Current:** {account_data.get('displayName', 'N/A')}\n"
            f"> **Last changed:** {last_name_change_timestamp and format_dt(datetime.fromtimestamp(last_name_change_timestamp), 'D')}\n"
            f"> **Changes:** {account_data.get('numberOfDisplayNameChanges', 0)}"
        )
        if account_data.get('canUpdateDisplayName', False):
            display_name_current += f"\n> **Updatable:** {chk}"
        
        embed.add_field(name="Display Name:", value=display_name_current, inline=False)
        
        last_login_timestamp = None
        if account_data.get('lastLogin'):
            last_login = datetime.fromisoformat(account_data.get('lastLogin').replace('Z', '+00:00'))
            last_login_timestamp = int(last_login.timestamp())
        
        login_section = (
            f"**Failed Login Attempts:** {account_data.get('failedLoginAttempts', '0')}\n"
            f"> **Last Login:** {last_login_timestamp and format_dt(datetime.fromtimestamp(last_login_timestamp), 'D')}\n"
            f"> **Two Factor Authentication:** {f'{chk}' if account_data.get('tfaEnabled', False) else f'{fail}'}"
        )
        embed.add_field(name="Login:", value=f"> {login_section}", inline=False)
        
        country = account_data.get('country', 'Unknown')
        preferred_language = account_data.get('preferredLanguage', 'en')
        
        embed.add_field(name="Country:", value=f"> {country}", inline=True)
        embed.add_field(name="Preferred Language:", value=f"> {preferred_language}", inline=True)
        
        if avatar:
            embed.set_thumbnail(url=avatar)
        
        await ctx.respond(embed=embed, ephemeral=True)
    except Exception as e:
        print(f"Error fetching account info: {str(e)}")
        await ctx.respond(embed=discord.Embed(
            title=f"Error {fail}",
            description="An error occurred while fetching account information.",
            color=discord.Color.red()
        ), ephemeral=True)

@bot.slash_command(name="custom-level", description="Allows you to set a custom BR level")
@commands.cooldown(1, 5,commands.BucketType.user)
async def customlevel(ctx, level: discord.Option(int, description="Custom Level",min_value=-999999, max_value=999999, required=True)):
    await ctx.defer()

    await UpdateInfoAccount(ctx.author.id)

    user_data = await db.get_user_data(ctx.author.id)
    
    if not user_data:
        await ctx.respond(embed=NotLoggedIn)
        return

    current_selected = user_data.get('selected', 0)
    accounts = user_data.get('accounts', [])
    
    if not accounts:
        await ctx.respond(embed=NotLoggedIn)
        return

    await UpdateInfoAccount(ctx.author.id)

    current_account = accounts[current_selected]
    access_token = current_account['AccessToken']
    account_id = current_account['AccountId']
    display_name = current_account['Display Name']
    avatar = await FetchAvatarUser(ctx.author.id)

    g_chan = 1346259089508008057
    GLOBAL_CHANNEL = int(g_chan)
    global_crash = bot.get_channel(GLOBAL_CHANNEL)

    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/user/{account_id}"

    response = requests.get(url, headers=headers)
    response_data = response.json()

    if 'current' not in response_data or not response_data['current']:
        embed = discord.Embed(
            title=f"{fail} Error",
            description=f"You are not in a **party** on **{display_name}**",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=avatar)
        await ctx.respond(embed=embed)
        return

    party_id = response_data['current'][0]['id']
    url = f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/parties/{party_id}/members/{account_id}"

    data = {
        "Default:AthenaBannerInfo_j": json.dumps({
            "AthenaBannerInfo": {
                "seasonLevel": level
            }
        })
    }

    body = {
        'delete': [],
        'revision': 1,
        'update': data
    }

    url = f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/parties/{party_id}/members/{account_id}/meta"
    response = requests.patch(url=url, headers=headers, json=body)
    if response.status_code == 200:
        embed = discord.Embed(
            description=f"{chk} Your level is now **{level}**\n\n**(Level not shown to you)**\nShown to Party Members Only",
            color=discord.Color.green()
        )
        embed.set_author(name=f'{display_name}', icon_url=avatar)
        await ctx.respond(embed=embed)
    elif 'errors.com.epicgames.account.invalid_account_credentials' in str(response.text):
        await ctx.respond(embed=CredentialsExpired, ephemeral=True)
    elif response.status_code != 400:
        titolo = response.json()['errorCode']
        if titolo == 'errors.com.epicgames.social.party.stale_revision':
            
            mexvars = response.json()['messageVars']
            revision = max(mexvars)
            
            body = {
                'delete': [],
                'revision': revision,
                'update': data
            }
            
            url = f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/parties/{party_id}/members/{account_id}/meta"
            response = requests.patch(url=url, headers=headers, json=body)
            embed = discord.Embed(
                description=f"{chk} Your level is now **{level}**\n\nVisible to Party Members Only",
                color=discord.Color.green()
            )
            embed.set_author(name=f'{display_name}', icon_url=avatar)
            await ctx.respond(embed=embed)

            await asyncio.sleep(5)

            global_embed = discord.Embed(description=f"🌐 **Global Level Equip Detected!**\n> **User:** `{display_name}`", color=discord.Color.yellow())
            global_embed.set_footer(text=f'{account_id}',icon_url=avatar)
            await global_crash.send(embed=global_embed)
        else:
            embed = discord.Embed(
                title=f"{fail} Error",
                description=f"Failed to set your level.",
                color=discord.Color.red()
            )
            await ctx.respond(embed=embed)

@bot.slash_command(name="custom-crowns", description="Allows you to set your crown wins")
@commands.cooldown(1, 5,commands.BucketType.user)
async def customcrowns(ctx, crowns: discord.Option(int, description="Custom Crowns", required=True,min_value=1, max_value=99999)):
    await ctx.defer()

    await UpdateInfoAccount(ctx.author.id)

    user_data = await db.get_user_data(ctx.author.id)
    
    if not user_data:
        await ctx.respond(embed=NotLoggedIn)
        return

    current_selected = user_data.get('selected', 0)
    accounts = user_data.get('accounts', [])
    
    if not accounts:
        await ctx.respond(embed=NotLoggedIn)
        return

    await UpdateInfoAccount(ctx.author.id)

    current_account = accounts[current_selected]
    access_token = current_account['AccessToken']
    account_id = current_account['AccountId']
    display_name = current_account['Display Name']
    avatar = await FetchAvatarUser(ctx.author.id)

    g_chan = 1346259089508008057
    GLOBAL_CHANNEL = int(g_chan)
    global_crash = bot.get_channel(GLOBAL_CHANNEL)

    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/user/{account_id}"

    response = requests.get(url, headers=headers)
    response_data = response.json()

    if 'current' not in response_data or not response_data['current']:
        embed = discord.Embed(
            title=f"{fail} Error",
            description=f"You are not in a **party** on **{display_name}**",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=avatar)
        await ctx.respond(embed=embed)
        return

    party_id = response_data["current"][0]["id"]

    member_data = None
    member_meta = None
    for member in response_data["current"][0]["members"]:
        if member["account_id"] == account_id:
            member_data = member
            member_meta = member.get("meta", {})
            break

    cosmetic_loadout_data = None
    if member_meta and "Default:AthenaCosmeticLoadout_j" in member_meta:
        cosmetic_loadout_data = member_meta["Default:AthenaCosmeticLoadout_j"]
    
    loadout_data = {}
    if cosmetic_loadout_data:
        try:
            existing_loadout = json.loads(cosmetic_loadout_data)
            if "AthenaCosmeticLoadout" in existing_loadout:
                existing_loadout["AthenaCosmeticLoadout"]["cosmeticStats"] = [
                    {
                        "statName": "TotalVictoryCrowns",
                        "statValue": crowns
                    },
                    {
                        "statName": "TotalRoyalRoyales",
                        "statValue": crowns
                    },
                    {
                        "statName": "HasCrown",
                        "statValue": 0
                    }
                ]
                loadout_data = {
                    "Default:AthenaCosmeticLoadout_j": json.dumps(existing_loadout)
                }
            else:
                loadout_data = {
                    "Default:AthenaCosmeticLoadout_j": json.dumps({
                        "AthenaCosmeticLoadout": json.dumps({
                            "cosmeticStats": [
                                {
                                    "statName": "TotalVictoryCrowns",
                                    "statValue": crowns
                                },
                                {
                                    "statName": "TotalRoyalRoyales",
                                    "statValue": crowns
                                },
                                {
                                    "statName": "HasCrown",
                                    "statValue": 0
                                }
                            ]
                        })
                    })
                }
        except:
            loadout_data = {
                "Default:AthenaCosmeticLoadout_j": json.dumps({
                    "AthenaCosmeticLoadout": json.dumps({
                        "cosmeticStats": [
                            {
                                "statName": "TotalVictoryCrowns",
                                "statValue": crowns
                            },
                            {
                                "statName": "TotalRoyalRoyales",
                                "statValue": crowns
                            },
                            {
                                "statName": "HasCrown",
                                "statValue": 0
                            }
                        ]
                    })
                })
            }
    else:
        loadout_data = {
            "Default:AthenaCosmeticLoadout_j": json.dumps({
                "AthenaCosmeticLoadout": json.dumps({
                    "cosmeticStats": [
                        {
                            "statName": "TotalVictoryCrowns",
                            "statValue": crowns
                        },
                        {
                            "statName": "TotalRoyalRoyales",
                            "statValue": crowns
                        },
                        {
                            "statName": "HasCrown",
                            "statValue": 0
                        }
                    ]
                })
            })
        }
    
    emote_data = {
        "Default:FrontendEmote_j": json.dumps({
            "FrontendEmote": {
                "emoteItemDef": "/BRCosmetics/Athena/Items/Cosmetics/Dances/EID_Coronet.EID_Coronet",
                "emoteEKey": "",
                "emoteSection": -1,
                "multipurposeEmoteData": -1
            }
        })
    }
    
    loadout_body = {
        'delete': [],
        'revision': member_data.get('revision', 1),
        'update': loadout_data
    }
    
    emote_body = {
        'delete': [],
        'revision': member_data.get('revision', 1) + 1,
        'update': emote_data
    }
    
    url1 = f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/parties/{party_id}/members/{account_id}/meta"
    response = requests.patch(url=url1, headers=headers, json=loadout_body)
    await asyncio.sleep(3)
    response2 = requests.patch(url=url1, headers=headers, json=emote_body)

    if response.status_code == 204 and response2.status_code == 204:
        embed = discord.Embed(
            description=f"{chk} Your **crown wins** have been **set to {crowns}**\n\n**(Crowns not shown to you)**\nShown to Party Members Only",
            color=discord.Color.green()
        )
        embed.set_author(name=f'{display_name}', icon_url=avatar)
        embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/991129536076984380.webp?size=96&quality=lossless")
        await ctx.respond(embed=embed)
    elif 'errors.com.epicgames.account.invalid_account_credentials' in str(response.text or response2):
        await ctx.respond(embed=CredentialsExpired)
    else:
        titolo = response.json()['errorCode']
        if titolo == 'errors.com.epicgames.social.party.stale_revision':
            
            mexvars = response.json()['messageVars']
            revision = max(mexvars)
            
            body = {
                'delete': [],
                'revision': revision,
                'update': loadout_data
            }
            
            url2 = f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/parties/{party_id}/members/{account_id}/meta"
            response = requests.patch(url=url2, headers=headers, json=body)
            response2 = requests.patch(url=url2, headers=headers, json=emote_body)
            embed = discord.Embed(
                description=f"{chk} Your **crown wins** have been **set to {crowns}**\n\nVisible to Party Members Only",
                color=discord.Color.green()
            )
            embed.set_author(name=f'{display_name}', icon_url=avatar)
            embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/991129536076984380.webp?size=96&quality=lossless")
            await ctx.respond(embed=embed)

            await asyncio.sleep(5)

            global_embed = discord.Embed(description=f"🌐 **Global Crown Equip Detected!**\n> **User:** `{display_name}`", color=discord.Color.yellow())
            global_embed.set_footer(text=f'{account_id}',icon_url=avatar)
            await global_crash.send(embed=global_embed)

@bot.slash_command(name="skip-tutorial", description="Skips the Save the World tutorial")
@commands.cooldown(1, 5,commands.BucketType.user)
async def skip_tutorial(ctx):
    await ctx.defer()

    user_data = await db.get_user_data(ctx.author.id)
    
    if not user_data:
        await ctx.respond(embed=NotLoggedIn)
        return

    current_selected = user_data.get('selected', 0)
    accounts = user_data.get('accounts', [])
    
    if not accounts:
        await ctx.respond(embed=NotLoggedIn)
        return

    await UpdateInfoAccount(ctx.author.id)

    current_account = accounts[current_selected]
    access_token = current_account['AccessToken']
    account_id = current_account['AccountId']
    display_name = current_account['Display Name']
    avatar = await FetchAvatarUser(ctx.author.id)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    url = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/SkipTutorial?profileId=campaign&rvn=-1"

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, data='{}') as response:
            if response.status == 204 or response.status == 200:
                embed = discord.Embed(
                    description=f"{chk} Successfully skipped the Save the World tutorial.",
                    color=discord.Color.green()
                )
                embed.set_author(name=f'{display_name}', icon_url=avatar)
            elif 'errors.com.epicgames.account.invalid_account_credentials' in str(await response.text()):
                await ctx.respond(embed=CredentialsExpired, ephemeral=True)
                return
            elif response.status != 400:
                embed = discord.Embed(
                    description=f"{fail} Failed to skip the tutorial.",
                    color=discord.Color.red()
                )
            await ctx.respond(embed=embed, ephemeral=True)

class Kick(discord.ui.Modal):
    def __init__(self, token, account_id, *args, **kwargs):
        self.token = token
        self.account_id = account_id
        super().__init__(title="Party Menu | Kick", *args, **kwargs)
        self.add_item(
            discord.ui.InputText(
                label="Username",
                placeholder="...",
                style=discord.InputTextStyle.short
            )
        )

    async def callback(self, interaction: discord.Interaction):
        playername = self.children[0].value

        user_data = await db.get_user_data(interaction.user.id)
        
        if not user_data:
            await interaction.response.send_message(embed=NotLoggedIn, ephemeral=True)
            return

        current_selected = user_data.get('selected', 0)
        accounts = user_data.get('accounts', [])
        
        if not accounts:
            await interaction.response.send_message(embed=NotLoggedIn, ephemeral=True)
            return

        await UpdateInfoAccount(interaction.user.id)

        current_account = accounts[current_selected]
        access_token = current_account['AccessToken']
        account_id = current_account['AccountId']

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        url = f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/displayName/{playername}"
        res = requests.get(url, headers=headers)

        try:
            if res.status_code == 200:
                member_id = res.json()["id"]
                if member_id == account_id:
                    not_found = discord.Embed(description=f"{fail} You cant kick yourself!", color=discord.Color.red())
                    await interaction.response.send_message(embed=not_found, ephemeral=True)

                party_req = requests.get(f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/user/{account_id}", headers=headers)
                if party_req.status_code == 200:
                    party_id = party_req.json()['current'][0]['id']

                    requests.delete(f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/parties/{party_id}/members/{member_id}", headers=headers)  

                    embed = discord.Embed(
                        title = f"{chk} User kicked successfully!",
                        colour=discord.Colour.brand_green()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    not_found = discord.Embed(description=f"{fail} You arent in a party!", color=discord.Color.red())
                    await interaction.response.send_message(embed=not_found, ephemeral=True)
            elif res.status_code != 400:
                not_found = discord.Embed(description=f"{fail} User doesnt exist!", color=discord.Color.red())
                await interaction.response.send_message(embed=not_found, ephemeral=True)
        except:
            await interaction.response.send_message(embed=UnknownError, ephemeral=True)

def chunk_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

@bot.slash_command(name="party-menu", description="Displays a menu for your current party")
@commands.cooldown(1, 5, commands.BucketType.user)
async def partymenu(ctx):
    await ctx.defer()

    user_data = await db.get_user_data(ctx.author.id)
    
    if not user_data:
        await ctx.respond(embed=NotLoggedIn)
        return

    current_selected = user_data.get('selected', 0)
    accounts = user_data.get('accounts', [])
    
    if not accounts:
        await ctx.respond(embed=NotLoggedIn)
        return

    await UpdateInfoAccount(ctx.author.id)

    current_account = accounts[current_selected]
    access_token = current_account['AccessToken']
    account_id = current_account['AccountId']
    display_name = current_account['Display Name']
    avatar = await FetchAvatarUser(ctx.author.id)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Fetch Party Information
    party_req = requests.get(f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/user/{account_id}", headers=headers)

    if party_req.status_code != 200:
        not_found = discord.Embed(description=f"{fail} You aren't in a party!", color=discord.Color.red())
        await ctx.respond(embed=not_found)
        return

    party_data = party_req.json()
    members_data = party_data['current'][0]['members']
    
    # Collect all member IDs
    member_ids = [member['account_id'] for member in members_data]
    
    # Fetch Display Names in Batches of 100
    display_names = {}
    for chunk in chunk_list(member_ids, 100):  
        ids = ','.join(chunk)
        url = f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{ids}"
        res = requests.get(url, headers=headers)

        if res.status_code == 200:
            for user in res.json():
                display_names[user['id']] = user['displayName']

    # Create Embed
    embd = discord.Embed(
        title="Party Menu",
        description="Please select the action you would like to do in your current party!",
        color=discord.Color.blurple()
    )
    embd.set_thumbnail(url=avatar)

    # Create Buttons
    view = discord.ui.View(timeout=None)
    button_kick = discord.ui.Button(style=discord.ButtonStyle.red, label="Kick")
    button_kick_all = discord.ui.Button(style=discord.ButtonStyle.red, label="Kick All")
    button_leave = discord.ui.Button(style=discord.ButtonStyle.green, label="Leave")

    async def callback_kick(interaction):
        if interaction.user.id != ctx.author.id:
            embed = discord.Embed(description="❌ You are not the Command Author", color=discord.Color.brand_red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        modal = Kick(access_token, account_id)
        await interaction.response.send_modal(modal)

    async def callback_kick_all(interaction):
        if interaction.user.id != ctx.author.id:
            embed = discord.Embed(description="❌ You are not the Command Author", color=discord.Color.brand_red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        try:
            for member in members_data:
                if member['account_id'] != account_id:
                    requests.delete(f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/parties/{party_data['current'][0]['id']}/members/{member['account_id']}", headers=headers)

            embed = discord.Embed(title=f"{chk} Kicked everyone successfully!", colour=discord.Colour.brand_green())
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except:
            await interaction.response.send_message(embed=UnknownError, ephemeral=True)

    async def callback_leave(interaction):
        if interaction.user.id != ctx.author.id:
            embed = discord.Embed(description="❌ You are not the Command Author", color=discord.Color.brand_red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        try:
            requests.delete(f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/parties/{party_data['current'][0]['id']}/members/{account_id}", headers=headers)
            embed = discord.Embed(title=f"{chk} Left party successfully!", colour=discord.Colour.brand_green())
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except:
            await interaction.response.send_message(embed=UnknownError, ephemeral=True)

    button_kick.callback = callback_kick
    button_kick_all.callback = callback_kick_all
    button_leave.callback = callback_leave

    view.add_item(button_kick)
    view.add_item(button_kick_all)
    view.add_item(button_leave)

    await ctx.respond(embed=embd, view=view)

current_fn_bots = {}

@bot.slash_command(name="custom-status", description="Allows you to set a custom status while your offline")
async def custom_status(ctx, status: discord.Option(str, "The status you want to set")):
    await ctx.defer()

    user_data = await db.get_user_data(ctx.author.id)
    
    if not user_data:
        await ctx.respond(embed=NotLoggedIn)
        return

    current_selected = user_data.get('selected', 0)
    accounts = user_data.get('accounts', [])
    
    if not accounts:
        await ctx.respond(embed=NotLoggedIn)
        return

    await UpdateInfoAccount(ctx.author.id)
        
    current_account = accounts[current_selected]
    access_token = current_account['AccessToken']
    account_id = current_account['AccountId'] 
    device_id = current_account['DeviceID']
    secret = current_account['Secret']
    display_name = current_account['Display Name']

    bot_key = f"{ctx.author.id}_{account_id}"
    
    if bot_key in current_fn_bots:
        await current_fn_bots[bot_key].close()
        del current_fn_bots[bot_key]

    try:
        import rebootpy
        from rebootpy.ext import commands as fncommands

        fn_bot = fncommands.Bot(
            command_prefix='!',
            auth=rebootpy.DeviceAuth(
                device_id=device_id,
                account_id=account_id,
                secret=secret
            )
        )
        
        current_fn_bots[bot_key] = fn_bot

        @fn_bot.event
        async def event_ready():
            fn_bot.set_presence(status=status)
            
            class StatusView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=None)

                @discord.ui.button(label="Stop Status", style=discord.ButtonStyle.red)
                async def stop_button(self, button: discord.ui.Button, interaction: discord.Interaction):
                    if interaction.user.id != ctx.author.id:
                        embed = discord.Embed(description="❌ You are not the Command Author", color=discord.Color.brand_red())
                        return await interaction.response.send_message(embed=embed, ephemeral=True)

                    if bot_key in current_fn_bots:
                        await current_fn_bots[bot_key].close()
                        del current_fn_bots[bot_key]
                        
                        stop_embed = discord.Embed(
                            title="Status Stopped",
                            description="Your custom status has been stopped.",
                            color=discord.Color.red()
                        )
                        await interaction.response.edit_message(embed=stop_embed, view=None)
                    else:
                        await interaction.response.send_message(
                            "Status was already stopped.", 
                            ephemeral=True
                        )

            embed = discord.Embed(
                title="Status Updated",
                description=f'Set your status to `{status}`\nClick the button below to stop the status at any time',
                color=discord.Color.green()
            )
            embed.set_footer(text="Note: Only use this when you are offline or you will get logged out continuously until you stop the status.")
            await ctx.respond(embed=embed, view=StatusView(), ephemeral=True)

        await fn_bot.start()

    except Exception as e:
        if bot_key in current_fn_bots:
            del current_fn_bots[bot_key]
        await ctx.respond(
            embed=discord.Embed(
                title="Error",
                description=f"Failed to set status: {str(e)}",
                color=discord.Color.red()
            ),
            ephemeral=True
        )

@bot.slash_command(name="send-invite", description="Sends a party invite to a specified player on your friends list")
@commands.cooldown(1, 5,commands.BucketType.user)
async def Send(ctx, user: Option(str, "User to invite.")):
    await ctx.defer()

    await UpdateInfoAccount(ctx.author.id)

    user_data = await db.get_user_data(ctx.author.id)
    
    if not user_data:
        await ctx.respond(embed=NotLoggedIn)
        return

    current_selected = user_data.get('selected', 0)
    accounts = user_data.get('accounts', [])
    
    if not accounts:
        await ctx.respond(embed=NotLoggedIn)
        return

    await UpdateInfoAccount(ctx.author.id)

    current_account = accounts[current_selected]
    access_token = current_account['AccessToken']
    account_id = current_account['AccountId']
    display_name = current_account['Display Name']

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    party_req = requests.get(f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/user/{account_id}", headers=headers)
    if party_req.status_code == 200:
        partyid = party_req.json()['current'][0]['id'] # check if your in a party
    else:
        await ctx.respond(embed=UnknownError)
        return

    url = f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/displayName/{user}" # user your inviting (conv user --> ID)
    res = requests.get(url, headers=headers)

    try:
        if res.json():
            targetid = res.json()["id"] # user your inviting
            
            bodyInv = json.dumps({
                "epic:fg:build-id_s": "1:3:",
                "epic:conn:platform_s": "WIN",
                "epic:conn:type_s": "game",
                "epic:invite:platform_data_s": "",
                "epic:member:dn_s": ""
            })
            res2 = requests.post(f"https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite/parties/{partyid}/invites/{targetid}?sendPing=true", headers=headers, data=bodyInv)
            if res2.status_code == 200 or res2.status_code == 204:
                enabled = discord.Embed(title=f"{chk} Successfully sent invite!", color=discord.Color.green())
                await ctx.respond(embed=enabled, ephemeral=False)
            elif 'errors.com.epicgames.account.invalid_account_credentials' in str(res2.text):
                await ctx.respond(embed=CredentialsExpired, ephemeral=True)
            elif res2.status_code != 400:
                print(res2.text)
                await ctx.respond(embed=UnknownError)
    except:
        await ctx.respond(embed=UnknownError)

@bot.slash_command(name="gifts-received", description="View your history of received gifts")
async def gifts_received(ctx: discord.ApplicationContext):
    await ctx.defer()

    user_data = await db.get_user_data(ctx.author.id)
    
    if not user_data:
        await ctx.respond(embed=NotLoggedIn)
        return

    current_selected = user_data.get('selected', 0)
    accounts = user_data.get('accounts', [])
    
    if not accounts:
        await ctx.respond(embed=NotLoggedIn)
        return

    await UpdateInfoAccount(ctx.author.id)

    current_account = accounts[current_selected]
    access_token = current_account['AccessToken']
    account_id = current_account['AccountId']
    display_name = current_account['Display Name']
    avatar = await FetchAvatarUser(ctx.author.id)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/QueryProfile?profileId=common_core&rvn=-1",
            headers=headers,
            data="{}"
        )
        response.raise_for_status()
        profile_data = response.json()

        gifts_received = profile_data['profileChanges'][0]['profile']['stats']['attributes']['gift_history']['receivedFrom']
        
        if not gifts_received:
            embed = discord.Embed(
                title="Gift History",
                description=f"**{display_name}** hasn't received any gifts yet!",
                color=discord.Color.blue()
            )
            await ctx.followup.send(embed=embed)
            return

        processed_gifts = []
        for sender_id, timestamp in gifts_received.items():
            try:
                sender_response = requests.get(
                    f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{sender_id}",
                    headers=headers
                )
                sender_data = sender_response.json()
                sender_name = sender_data.get('displayName', 'Unknown User')
                
                date_obj = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
                unix_timestamp = int(date_obj.timestamp())
                date_received = f"<t:{unix_timestamp}:F>"
                
                processed_gifts.append((sender_name, date_received))
            except Exception as e:
                continue

        gifts_per_page = 10
        pages = []
        
        for i in range(0, len(processed_gifts), gifts_per_page):
            page_gifts = processed_gifts[i:i + gifts_per_page]
            
            embed = discord.Embed(
                title="Gift History",
                description=f"**{display_name}** has received **{len(gifts_received)}** gifts\nPage {i//gifts_per_page + 1}/{(len(processed_gifts)-1)//gifts_per_page + 1}",
                color=discord.Color.blue()
            )
            embed.set_author(name=display_name, icon_url=avatar)
            
            for idx, (sender_name, date_received) in enumerate(page_gifts, start=i+1):
                embed.add_field(
                    name=f"Gift #{idx}",
                    value=f"From: **{sender_name}**\nReceived: {date_received}",
                    inline=False
                )
            
            pages.append(embed)

        class GiftPaginationView(discord.ui.View):
            def __init__(self, ctx):
                super().__init__(timeout=180)
                self.current_page = 0
                self.ctx = ctx

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                if interaction.user.id != self.ctx.author.id:
                    embed = discord.Embed(description="❌ You cannot use this button", color=discord.Color.brand_red())
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return False
                return True

            @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray, disabled=True)
            async def previous_button(self, button: discord.ui.Button, interaction: discord.Interaction):
                self.current_page = max(0, self.current_page - 1)
                
                self.previous_button.disabled = self.current_page == 0
                self.next_button.disabled = self.current_page == len(pages) - 1
                
                await interaction.response.edit_message(embed=pages[self.current_page], view=self)

            @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
            async def next_button(self, button: discord.ui.Button, interaction: discord.Interaction):
                self.current_page = min(len(pages) - 1, self.current_page + 1)
                
                self.previous_button.disabled = self.current_page == 0
                self.next_button.disabled = self.current_page == len(pages) - 1
                
                await interaction.response.edit_message(embed=pages[self.current_page], view=self)

        if pages:
            view = GiftPaginationView(ctx)
            view.next_button.disabled = len(pages) <= 1
            await ctx.followup.send(embed=pages[0], view=view)
        else:
            embed = discord.Embed(
                title="Gift History",
                description=f"**{display_name}** has no valid gifts to display",
                color=discord.Color.blue()
            )
            await ctx.followup.send(embed=embed)

    except Exception as e:
        error_embed = discord.Embed(
            title="Error",
            description=f"An error occurred while fetching gift history: {str(e)}",
            color=discord.Color.red()
        )
        await ctx.followup.send(embed=error_embed)

@bot.slash_command(name="join-map", description="Load into a Creative map using a map code")
async def load_map(ctx, mapcode: str):
    await ctx.defer()
    
    user_data = await db.get_user_data(ctx.author.id)
    
    if not user_data:
        await ctx.respond(embed=NotLoggedIn)
        return

    current_selected = user_data.get('selected', 0)
    accounts = user_data.get('accounts', [])
    
    if not accounts:
        await ctx.respond(embed=NotLoggedIn)
        return

    await UpdateInfoAccount(ctx.author.id)

    current_account = accounts[current_selected]
    access_token = current_account['AccessToken']
    account_id = current_account['AccountId']
    display_name = current_account['Display Name']

    try:
        exchange_url = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/exchange"
        exchange_headers = {
            "Authorization": f"Bearer {access_token}"
        }

        exchange_response = requests.get(exchange_url, headers=exchange_headers)
        if exchange_response.status_code != 200:
            await ctx.followup.send(
                embed=discord.Embed(
                    title="Error",
                    description="Failed to exchange token",
                    color=discord.Color.red()
                )
            )
        elif 'errors.com.epicgames.account.invalid_account_credentials' in str(exchange_response.text):
            await ctx.respond(embed=CredentialsExpired, ephemeral=True)
            return

        exchange_code = exchange_response.json().get('code')

        eg1_url = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token?token_type=eg1"
        eg1_headers = {
            'Authorization': 'Basic M2UxM2M1YzU3ZjU5NGE1NzhhYmU1MTZlZWNiNjczZmU6NTMwZTMxNmMzMzdlNDA5ODkzYzU1ZWM0NGYyMmNkNjI=',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        eg1_payload = f'grant_type=exchange_code&exchange_code={exchange_code}&token_type=eg1'

        eg1_response = requests.post(eg1_url, headers=eg1_headers, data=eg1_payload)
        if eg1_response.status_code != 200:
            await ctx.followup.send(
                embed=discord.Embed(
                    title="Error",
                    description="Failed to get EG1 token",
                    color=discord.Color.red()
                )
            )
            return

        eg1_token = eg1_response.json().get('access_token')

        launch_url = f"https://content-service.bfda.live.use1a.on.epicgames.com/api/content/v2/launch/link/{mapcode}"
        launch_headers = {
            "Authorization": f"Bearer {eg1_token}"
        }

        launch_response = requests.post(launch_url, headers=launch_headers)
        if launch_response.status_code != 200:
            await ctx.followup.send(
                embed=discord.Embed(
                    title="Error",
                    description=f"Failed to launch map with code: {mapcode}",
                    color=discord.Color.red()
                )
            )
            return

        status = launch_response.json().get("status")

        if status == "queued":
            embed = discord.Embed(
                title="Map Queued",
                description=f"Launch Fortnite to load map: `{mapcode}`",
                color=discord.Color.gold()
            )
            embed.set_author(name=display_name)
            embed.set_footer(text="The map will load when you launch Fortnite")
            await ctx.followup.send(embed=embed)
        
        elif status == "notified":
            embed = discord.Embed(
                title="Map Launched",
                description=f"Successfully loaded map: `{mapcode}`",
                color=discord.Color.green()
            )
            embed.set_author(name=display_name)
            await ctx.followup.send(embed=embed)
        
        else:
            await ctx.followup.send(
                embed=discord.Embed(
                    title="Error",
                    description=f"Unknown status: {status}",
                    color=discord.Color.red()
                )
            )

    except Exception as e:
        error_embed = discord.Embed(
            title="Error",
            description=f"An error occurred while loading the map: {str(e)}",
            color=discord.Color.red()
        )
        await ctx.followup.send(embed=error_embed)

@bot.slash_command(name="dupe", description="Displays a menu for duping in Save the World")
@commands.cooldown(1, 15, commands.BucketType.user)
async def dupemenu(ctx):
    await ctx.defer()

    user_data = await db.get_user_data(ctx.author.id)

    if not user_data:
        await ctx.respond(embed=NotLoggedIn)
        return

    current_selected = user_data.get('selected', 0)
    accounts = user_data.get('accounts', [])

    if not accounts:
        await ctx.respond(embed=NotLoggedIn)
        return

    await UpdateInfoAccount(ctx.author.id)

    current_account = accounts[current_selected]
    display_name = current_account['Display Name']
    avatar = await FetchAvatarUser(ctx.author.id)

    GUI = Panel2(author_id=ctx.author.id)
    embed = discord.Embed(
        title=f"Dupe Menu for {display_name}",
        colour=discord.Colour.gold()
    )
    await ctx.respond(embed=embed, view=GUI, ephemeral=True)

@bot.event
async def on_ready():
    print("Bot is online.")
    print(f"Logged in as {bot.user}")

    # Start the UptimeRobot keep-alive server
    await start_web_server()

    try:
        await bot.sync_commands()
        print(f"Slash commands synced! Total: {len(bot.commands)}")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# Start the bot with the web server
async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
