import discord
import json
import os
import asyncio
import aiohttp
import requests
import pytz
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
from discord.ext import commands, tasks
from discord.commands import slash_command

intents = discord.Intents.all()
bot = discord.Bot(intents=intents)
# courtesy of nocturnostw.xyz 

#bot uses py-cord not discord.py

TOKEN = os.getenv('bot_token')

class MemoryDatabase:
    def __init__(self):
        self.data = {}

    async def get_user_data(self, user_id):
        return self.data.get(str(user_id))

    async def update_user_data(self, user_id, new_data):
        self.data[str(user_id)] = new_data

db = MemoryDatabase()

ld = "<a:loading:1327704298942889994>"
chk = "<a:check:1327704217682575390>"
fail = "<a:fail:1342302818261930035>"
xl_emoji = "<:xl:1352872272616231025>"
dsc_emoji = "<a:dsc_symbol:1352872246322135103>"

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
        # courtesy of nocturnostw.xyz 
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
                    'grant_type': 'device_auth',
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
        # courtesy of nocturnostw.xyz 
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
    # courtesy of nocturnostw.xyz 

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
    
                embed2 = discord.Embed(description="Your profile has **unlocked**, you can now click **Start** to enable the dupe!", color=discord.Color.green())
                embed2.set_author(name=display_name, icon_url=avatar)
                await message.edit(embed=embed2, view=None)
                await interaction.followup.send(f"{interaction.user.mention} Your timer has ended!")
                break
            elif 'errors.com.epicgames.account.invalid_account_credentials' in str(req.text):
                await interaction.followup.send(embed=CredentialsExpired, ephemeral=True)
            elif req.status_code != 400:
                await interaction.followup.send(embed=UnknownError, ephemeral=True)
                break
            # courtesy of nocturno

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

                global_embed = discord.Embed(description=f"🌐 **Global Dupe Enable Detected!**\n> **User:** `{display_name}`", color=discord.Color.yellow())
                global_embed.set_footer(text=f'{account_id}',icon_url=avatar)
                await global_crash.send(embed=global_embed)
            elif 'errors.com.epicgames.account.invalid_account_credentials' in str(response2.text):
                await interaction.followup.send(embed=CredentialsExpired, ephemeral=True)
            elif response2.status_code != 400:
                failed = discord.Embed(description=f"{fail} Failed to enable dupe on **{display_name}**, if you need help join our support server https://discord.gg/enxl & open a support ticket with context of your problem! ", color=discord.Color.red())
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
    bot.sync_commands()


bot.run(bot_token)
