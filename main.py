import asyncio
import time
import discord
from discord import User, app_commands
import json
import uuid
import logging
import os
import sys
from datetime import datetime
import subprocess
from errors import ERRORS
import math

# Setup logging
if not os.path.exists("logs"):
    os.makedirs("logs")

today = datetime.now().strftime("%Y-%m-%d")
log_file = os.path.join("logs", f"{today}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

# Constants
DST_ROLE_ID = 1330291577607684107
EVOC_ROLE_ID = 1330291574814539786
PING_ROLE_ID = 1330291576202727567
INSTRUCTIONS_CHANNEL_ID = 1202417039893995651
TRAINING_LOG_FILE = "training_logs.json"
RESTART_INFO_FILE = "restart_info.json"
MAINTENANCE_FILE = "maintenance.json"
COOLDOWN_FILE = "training_cooldowns.json"
TRAINING_ID_FILE = "training_ids.json"
YOUR_DISCORD_USER_ID = 895170771830308865  # Replace with your actual user ID

def load_training_logs():
    try:
        with open(TRAINING_LOG_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logging.warning("Training log file not found, creating new log.")
        return {}

def save_training_logs(logs):
    with open(TRAINING_LOG_FILE, "w") as f:
        json.dump(logs, f, indent=4)
    logging.info("Training logs saved successfully.")


def load_training_cooldowns():
    if os.path.exists(COOLDOWN_FILE):
        with open(COOLDOWN_FILE, "r") as f:
            return json.load(f)
    return {}

def save_training_cooldowns(cooldowns):
    with open(COOLDOWN_FILE, "w") as f:
        json.dump(cooldowns, f, indent=4)

# Load existing IDs from the JSON file
def load_existing_ids():
    try:
        with open("training_ids.json", "r") as f:
            data = json.load(f)
            return data.get("ids", [])
    except FileNotFoundError:
        # If the file doesn't exist, return an empty list
        return []

# Save updated list of IDs to the JSON file
def save_existing_ids(ids):
    with open("training_ids.json", "w") as f:
        json.dump({"ids": ids}, f, indent=4)

intents = discord.Intents.all()
intents.members = True
intents.guilds = True
intents.message_content = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user}")

    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(type=discord.ActivityType.watching, name="Trainings")
    )

    try:
        synced = await tree.sync()
        logging.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logging.error(f"Command sync error: {e}")

    # Restart confirmation logic
    if os.path.exists(RESTART_INFO_FILE):
        try:
            with open(RESTART_INFO_FILE, "r") as f:
                restart_data = json.load(f)
            channel = bot.get_channel(restart_data["channel_id"])
            if channel:
                await channel.send(f"<@{restart_data['user_id']}>, ✅ Restart complete.")
                logging.info("Sent restart complete confirmation.")
            os.remove(RESTART_INFO_FILE)
        except Exception as e:
            logging.error(f"Failed to send restart complete message: {e}")

@tree.command(name="training", description="Log a LASD training session")
@app_commands.describe(
    available_time="When are you available?",
    group="Were you accepted into the group?"
)
async def training(interaction: discord.Interaction, available_time: str, group: bool):
    user = interaction.user
    roles = [role.id for role in user.roles]
    accepted = False

    if DST_ROLE_ID in roles:
        training_type = "DST"
    else:
        await interaction.response.send_message(
            "❌ You must have the DST role to use this command.",
            ephemeral=True
        )
        logging.warning(f"{user} tried to use /training without DST role.")
        return

    if not group:
        embed = discord.Embed(
            title="🚫 Training Not Submitted",
            description=(f"You must be **accepted into the group** to submit a training log.\n\n"
                         f"📌 Please review the steps in <#{INSTRUCTIONS_CHANNEL_ID}> before proceeding."),
            color=discord.Color.red()
        )
        embed.set_footer(text="Please contact staff for assistance.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Cooldown logic
    cooldowns = load_training_cooldowns()
    user_id = str(user.id)
    now = time.time()

    if user_id in cooldowns and now - cooldowns[user_id] < 3600:
        remaining = int(3600 - (now - cooldowns[user_id]))
        minutes = remaining // 60
        seconds = remaining % 60
        await interaction.response.send_message(
            f"⏳ You must wait {minutes}m {seconds}s before submitting another training. ERR CODE: LASD-E-2581",
            ephemeral=True
        )
        return

    # Generate LASD-Txxx ID
    logs = load_training_logs()
    existing_ids = load_existing_ids()
    next_id_num = 1
    if existing_ids:
        # Extract numeric parts and find max
        id_numbers = [int(k.split("LASD-DST")[-1]) for k in existing_ids]
        next_id_num = max(id_numbers) + 1

    training_id = f"LASD-DST{next_id_num:03d}"
    existing_ids.append(training_id)
    save_existing_ids(existing_ids)

    # Set cooldown
    cooldowns[user_id] = now
    save_training_cooldowns(cooldowns)

    logs[training_id] = {
        "username": user.name,
        "user_id": str(user.id),
        "training_type": training_type,
        "available_time": available_time,
        "group_status": group,
        "accepted": accepted,
        "message_id": None  # will update after sending
    }

    embed = discord.Embed(
        title="📋 LASD Training Log",
        description="This training entry has been successfully logged.",
        color=discord.Color.blue()
    )
    embed.add_field(name="👤 Username", value=user.mention, inline=True)
    embed.add_field(name="📘 Training Type", value=training_type, inline=True)
    embed.add_field(name="✅ Group Status", value="Yes", inline=True)
    embed.add_field(name="⏰ Available Time", value=available_time, inline=False)
    embed.add_field(name="🆔 Training ID", value=training_id, inline=False)
    embed.set_footer(text="Submitted via /training", icon_url=user.display_avatar.url)

    channel = interaction.guild.get_channel(1330460907729322014)
    message = await channel.send(
        content=f"<@&{PING_ROLE_ID}.>, <@{user.id}>",
        allowed_mentions=discord.AllowedMentions(roles=True, users=True),
        embed=embed
    )

    # Save message ID and update JSON
    logs[training_id]["message_id"] = message.id
    save_training_logs(logs)

    # DM confirmation with link
    training_url = f"https://discord.com/channels/{interaction.guild.id}/{message.channel.id}/{message.id}"
    dm_embed = discord.Embed(
        title="✅ Training Submitted",
        description=(
            "Your training has been successfully submitted and is awaiting a fto to approve it. Please be patient.\n\n"
            f"[📄 View Training Message]({training_url})"
        ),
        color=discord.Color.green()
    )
    dm_embed.set_footer(text="Thank you for your submission!")

    try:
        await user.send(embed=dm_embed)
    except discord.Forbidden:
        await interaction.response.send_message(
            "⚠️ Training submitted, but I couldn't DM you. Please enable DMs from server members.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "✅ Your training has been sent! Check your DMs for confirmation.",
            ephemeral=True
        )

@tree.command(name="error-info", description="Look up what an error code means")
@app_commands.describe(code="The error code to look up, e.g., LASD-E-1012")
async def error_info(interaction: discord.Interaction, code: str):
    code = code.upper()

    # Check if the code exists in the ERROR dictionary
    if code in ERRORS:
        # Prepare an embed for the error code
        embed = discord.Embed(
            title=f"🔎 **Error Code: {code}**",
            description=f"Here is the detailed information about **{code}**.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="⚠️ Error Description",
            value=ERRORS[code],
            inline=False
        )
        embed.add_field(
            name="📝 Suggested Action",
            value="Please contact the support team if you need assistance.",
            inline=False
        )
        embed.set_footer(text="LASD | Error Lookup Service")

        # Send the embed as the response
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        # If the code isn't found, show an error message
        embed = discord.Embed(
            title="❌ **Unknown Error Code**",
            description=f"The error code **{code}** does not exist or is invalid.",
            color=discord.Color.red()
        )
        embed.add_field(
            name="⚠️ Error Details",
            value="Please ensure that the code is correct and try again.",
            inline=False
        )
        embed.add_field(
            name="💬 Need Help?",
            value="If you're still unsure, please make a ticket and request <@895170771830308865> to be added.",
            inline=False
        )
        embed.set_footer(text="LASD | Error Lookup Service")

        # Send the embed with an error message
        await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="list-error-codes", description="List all available error codes and their meanings")
async def list_error_codes(interaction: discord.Interaction):
    # Constants
    ITEMS_PER_PAGE = 10  # Customize based on how many fit nicely in one embed

    error_items = list(ERRORS.items())
    total_pages = math.ceil(len(error_items) / ITEMS_PER_PAGE)

    # Function to generate an embed for a given page
    def generate_embed(page: int) -> discord.Embed:
        embed = discord.Embed(
            title="📘 LASD Error Code Directory",
            description=f"Showing page {page + 1} of {total_pages}",
            color=discord.Color.dark_blue()
        )
        start_index = page * ITEMS_PER_PAGE
        end_index = min(start_index + ITEMS_PER_PAGE, len(error_items))

        for code, desc in error_items[start_index:end_index]:
            embed.add_field(name=f"🔹 {code}", value=desc, inline=False)

        embed.set_footer(text="LASD | Use /error-info <code> for specific details")
        return embed

    # Start with page 0
    current_page = 0
    embed = generate_embed(current_page)

    # Create buttons for pagination
    class Paginator(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)  # Adjust timeout as needed

        @discord.ui.button(label="⏮️ Prev", style=discord.ButtonStyle.primary)
        async def prev_button(self, interaction_button: discord.Interaction, button: discord.ui.Button):
            nonlocal current_page
            if current_page > 0:
                current_page -= 1
                await interaction_button.response.edit_message(embed=generate_embed(current_page), view=self)
            else:
                await interaction_button.response.defer()

        @discord.ui.button(label="⏭️ Next", style=discord.ButtonStyle.primary)
        async def next_button(self, interaction_button: discord.Interaction, button: discord.ui.Button):
            nonlocal current_page
            if current_page < total_pages - 1:
                current_page += 1
                await interaction_button.response.edit_message(embed=generate_embed(current_page), view=self)
            else:
                await interaction_button.response.defer()

    await interaction.response.send_message(embed=embed, view=Paginator(), ephemeral=True)


@tree.command(name="training-evoc", description="Request an EVOC training session")
@app_commands.describe(
    available_time="When are you available?"
)
async def training_evoc(interaction: discord.Interaction, available_time: str):
    user = interaction.user
    roles = [role.id for role in user.roles]
    
    # Check if user has the Master Deputy role or higher
    allowed_roles = [1330289052125102201]  # Add more role IDs if needed
    if not any(role_id in roles for role_id in allowed_roles):
        await interaction.response.send_message(
            "❌ You must be a **Master Deputy** or higher to request EVOC training. ERR CODE: LASD-E-1751",
            ephemeral=True
        )
        logging.warning(f"{user} tried to use /training-evoc without permission.")
        return

    # Cooldown logic
    cooldowns = load_training_cooldowns()
    user_id = str(user.id)
    now = time.time()

    if user_id in cooldowns and now - cooldowns[user_id] < 3600:
        remaining = int(3600 - (now - cooldowns[user_id]))
        minutes = remaining // 60
        seconds = remaining % 60
        await interaction.response.send_message(
            f"⏳ You must wait {minutes}m {seconds}s before submitting another request.",
            ephemeral=True
        )
        return

    # Generate LASD-EVOCxxx ID
    logs = load_training_logs()
    existing_ids = load_existing_ids()
    next_id_num = 1
    if existing_ids:
        id_numbers = [int(k.split("LASD-EVOC")[-1]) for k in existing_ids if k.startswith("LASD-EVOC")]
        if id_numbers:
            next_id_num = max(id_numbers) + 1

    training_id = f"LASD-EVOC{next_id_num:03d}"
    existing_ids.append(training_id)
    save_existing_ids(existing_ids)

    cooldowns[user_id] = now
    save_training_cooldowns(cooldowns)

    logs[training_id] = {
        "username": user.name,
        "user_id": str(user.id),
        "training_type": "EVOC",
        "available_time": available_time,
        "group_status": True,
        "accepted": True,
        "message_id": None
    }

    embed = discord.Embed(
        title="🚗 EVOC Training Request",
        description="An EVOC training request has been successfully logged.",
        color=discord.Color.orange()
    )
    embed.add_field(name="👤 Username", value=user.mention, inline=True)
    embed.add_field(name="📘 Training Type", value="EVOC", inline=True)
    embed.add_field(name="✅ Group Status", value=f"N/A EVOC-18291 (ERR CODE LASD-E-1281)", inline=True)
    embed.add_field(name="⏰ Available Time", value=available_time, inline=False)
    embed.add_field(name="🆔 Training ID", value=training_id, inline=False)
    embed.set_footer(text="Submitted via /training-evoc", icon_url=user.display_avatar.url)

    channel = interaction.guild.get_channel(1330460907729322014)
    message = await interaction.channel.send(
        content=f"<@&{PING_ROLE_ID}.>, <@{user.id}>",
        allowed_mentions=discord.AllowedMentions(roles=True, users=True),
        embed=embed
    )

    logs[training_id]["message_id"] = message.id
    save_training_logs(logs)

    training_url = f"https://discord.com/channels/{interaction.guild.id}/{message.channel.id}/{message.id}"
    dm_embed = discord.Embed(
        title="✅ EVOC Training Submitted",
        description=(f"Your EVOC training request has been logged and is awaiting assignment.\n\n"
                     f"[📄 View Training Request]({training_url})"),
        color=discord.Color.green()
    )
    dm_embed.set_footer(text="Thank you for your submission!")

    try:
        await user.send(embed=dm_embed)
    except discord.Forbidden:
        await interaction.response.send_message(
            "⚠️ Request submitted, but I couldn't DM you. Please enable DMs from server members.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "✅ Your EVOC training request has been logged! Check your DMs for confirmation.",
            ephemeral=True
        )

@tree.command(name="training_results", description="Log training results for a trainee")
@app_commands.describe(
    trainee="The trainee's name.",
    score="The trainee's score.",
    status="Whether the trainee passed or failed.",
    training_type="The Type of traning EVOC or DST",
    side_notes="Any additional notes or comments."
)
async def training_results(interaction: discord.Interaction, trainee: str, score: str, status: str, training_type: str, side_notes: str = ""):
    # Check if the user has the required role
    required_role_id = 1330291576202727567  # The ID of the required role
    user_roles = [role.id for role in interaction.user.roles]  # Get all roles of the user
    
    # If the user doesn't have the required role
    if required_role_id not in user_roles:
        await interaction.response.send_message("❌ You don't have permission to log training results.", ephemeral=True)
        logging.warning(f"{interaction.user} tried to use /training-results without the required role.")
        return

    # Validate status to ensure it is either "Passed" or "Failed" (case-sensitive)
    if status not in ["Passed", "Failed"]:
        await interaction.response.send_message("❌ Invalid status. Please choose either 'Passed' or 'Failed'.", ephemeral=True)
        return

    # Set embed color based on the status
    color = discord.Color.green() if status == "Passed" else discord.Color.red()

    # Prepare the embed with the provided details
    embed = discord.Embed(
        title="📊 Training Results",
        description=f"Training results for **{trainee}**",
        color=color
    )
    embed.add_field(name="🧑‍🏫 Trainee", value=trainee, inline=False)
    embed.add_field(name="🔢 Score", value=score, inline=False)
    embed.add_field(name="✅ Status", value=status, inline=False)
    embed.add_field(name="📝 Side Notes", value=side_notes or "No additional notes.", inline=False)
    embed.add_field(name="📚 Traning Type", value=training_type, inline=False)
    embed.add_field(name="🖋️ Host", value=interaction.user.mention, inline=False)  # Add the host to the embed
    embed.set_footer(text="LASD | Training Results Logged")

    # Send the embed to the designated channel
    channel = interaction.guild.get_channel(1330460924993077278)
    if channel:
        await channel.send(content=f"{interaction.user.mention}, {trainee}", allowed_mentions=discord.AllowedMentions(users=True), embed=embed)
        await interaction.response.send_message("✅ Training results have been logged successfully!", ephemeral=True)
        logging.info(f"Training results for {trainee} logged by {interaction.user}.")
    else:
        await interaction.response.send_message("❌ Failed to find the designated channel for results.", ephemeral=True)
        logging.error("Failed to find the designated channel for results.")

@tree.command(name="training_accept", description="Accept a training submission by ID")
@app_commands.describe(training_id="Enter the training ID to accept.")
async def training_accept(interaction: discord.Interaction, training_id: str):
    if not any(role.id == 1330291576202727567 for role in interaction.user.roles):
        await interaction.response.send_message("❌ You don't have permission to accept training submissions.", ephemeral=True)
        logging.warning(f"{interaction.user} tried to accept a training without permission.")
        return

    logs = load_training_logs()
    if training_id not in logs:
        await interaction.response.send_message(f"❌ No training log found for ID {training_id}.", ephemeral=True)
        logging.warning(f"Training ID not found: {training_id}")
        return

    training_data = logs[training_id]
    if training_data['accepted'] == 'true':
        await interaction.response.send_message(f"❌ Training ID {training_id} has already been accepted.", ephemeral=True)
        return

    training_data['accepted'] = 'true'
    save_training_logs(logs)

    logging.info(f"Training ID {training_id} accepted by {interaction.user}")

    embed = discord.Embed(
        title="✅ Training Accepted",
        description=f"Training with ID {training_id} has been accepted.",
        color=discord.Color.green()
    )
    embed.add_field(name="Training accepted", value="Training acceptance confirmed.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

    user_to_notify = await interaction.guild.fetch_member(int(training_data["user_id"]))
    if user_to_notify:
        dm_embed = discord.Embed(
            title="✅ Training Request Accepted!",
            description=(
                "Your training request has been accepted! 🎉\n\n"
                "Please get ready for your training session. Here are a few things you should prepare:\n\n"
                "• **Prepare necessary materials** 📚\n"
                "• **Be on time and ready to participate** ⏰\n"
                "• **Be in the briefing room** 🏢\n"
                "• **Follow any further instructions from the training coordinator** 📋\n\n"
                "Good luck with your training, and make sure to give it your best! 💪"
            ),
            color=discord.Color.green()
        )
        await user_to_notify.send(embed=dm_embed)

        channel = interaction.guild.get_channel(1330460907729322014)
        notify_embed = discord.Embed(
            title="🚨 Training Request Accepted!",
            description=(
                f"<@{training_data['user_id']}>, your training request has been **accepted**!\n\n"
                "📩 Please check your **DMs** for instructions on how to get ready for your session."
            ),
            color=discord.Color.green()
        )
        notify_embed.set_footer(text="LASD Training Unit")
        await channel.send(embed=notify_embed)
    else:
        logging.error(f"User with ID {training_data['user_id']} not found.")
        await interaction.response.send_message(f"❌ The user with ID {training_data['user_id']} was not found or is not in the server.", ephemeral=True)

@tree.command(name="devmode", description="Toggle development mode (maintenance mode)")
async def devmode(interaction: discord.Interaction):
    if interaction.user.id != YOUR_DISCORD_USER_ID:
        await interaction.response.send_message("❌ You don't have permission to toggle dev mode.", ephemeral=True)
        logging.warning(f"{interaction.user} tried to toggle dev mode without permission.")
        return

    # Load current maintenance mode status
    maintenance_active = False
    if os.path.exists(MAINTENANCE_FILE):
        try:
            with open(MAINTENANCE_FILE, "r") as f:
                data = json.load(f)
                maintenance_active = data.get("maintenance", False)
        except Exception as e:
            logging.error(f"Error reading maintenance file: {e}")

    if maintenance_active:
        # Disable maintenance mode
        os.remove(MAINTENANCE_FILE)
        await bot.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(type=discord.ActivityType.watching, name="Trainings")
        )
        logging.info(f"Bot exited maintenance mode by {interaction.user}")
        await interaction.response.send_message("✅ Bot is now out of maintenance mode.", ephemeral=False)
    else:
        # Enable maintenance mode
        with open(MAINTENANCE_FILE, "w") as f:
            json.dump({"maintenance": True}, f)

        await bot.change_presence(
            status=discord.Status.dnd,
            activity=discord.Game(name="Down for maintenance")
        )
        logging.info(f"Bot entered maintenance mode by {interaction.user}")
        await interaction.response.send_message("🔧 Bot is now in maintenance mode (Dev Mode).", ephemeral=False)

@tree.command(name="restart", description="Restart the bot and update all packages (Admin only)")
async def restart(interaction: discord.Interaction):
    if interaction.user.id != YOUR_DISCORD_USER_ID:
        embed = discord.Embed(
            title="❌ Permission Denied",
            description="You don't have permission to restart the bot.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logging.warning(f"Unauthorized restart attempt by {interaction.user}")
        return

    await interaction.response.defer(ephemeral=False, thinking=True)
    logging.info(f"Bot update and restart initiated by {interaction.user}")

    try:
        start_time = time.perf_counter()

        # Upgrade pip
        pip_start = time.perf_counter()
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=True)
        pip_duration = time.perf_counter() - pip_start

        # Freeze and parse
        freeze_start = time.perf_counter()
        installed_packages = subprocess.check_output([sys.executable, "-m", "pip", "freeze"]).decode().splitlines()
        package_names = [pkg.split('==')[0] for pkg in installed_packages]
        freeze_duration = time.perf_counter() - freeze_start

        # Upgrade all packages
        upgrade_start = time.perf_counter()
        if package_names:
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade"] + package_names, check=True)
        upgrade_duration = time.perf_counter() - upgrade_start

        total_duration = time.perf_counter() - start_time
        eta = round(total_duration + 5)  # Buffer for restart

        embed = discord.Embed(
            title="♻️ Restarting Bot",
            description="✅ All packages have been updated. Restarting now...",
            color=discord.Color.green()
        )
        embed.add_field(name="📦 pip Upgrade Time", value=f"{pip_duration:.2f} seconds", inline=True)
        embed.add_field(name="📋 Freeze Parse Time", value=f"{freeze_duration:.2f} seconds", inline=True)
        embed.add_field(name="🔄 Packages Upgrade Time", value=f"{upgrade_duration:.2f} seconds", inline=True)
        embed.add_field(name="⏱️ Total Time", value=f"{total_duration:.2f} seconds", inline=True)
        embed.add_field(name="🕒 Estimated Restart Time", value=f"{eta} seconds", inline=False)
        embed.set_footer(text=f"Initiated by {interaction.user}", icon_url=interaction.user.display_avatar.url)

        await interaction.followup.send(embed=embed, ephemeral=False)
        logging.info(f"Estimated restart duration: {eta} seconds")

    except Exception as e:
        logging.error(f"Update failed: {e}")
        error_embed = discord.Embed(
            title="❌ Update Failed",
            description=f"An error occurred during the update:\n```{str(e)}```",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)
        return

    # Save restart info
    with open(RESTART_INFO_FILE, "w") as f:
        json.dump({
            "user_id": interaction.user.id,
            "channel_id": interaction.channel.id
        }, f)

    await bot.close()
    os.execv(sys.executable, [sys.executable] + sys.argv)

@bot.event
async def on_message(message: discord.Message):
    # Check if the message is from a bot to prevent bot-to-bot interaction
    if message.author.bot:
        return

    # Check if the message is in the restricted channel (with ID 1330460907729322014)
    if message.channel.id == 1330460907729322014:
        # Check if the user has the required role to send a message
        if "1330291576202727567" not in [role.id for role in message.author.roles]:
            # If the user doesn't have the role, delete the message and send a warning
            await message.delete()

            # Send a warning embed
            warning_embed = discord.Embed(
                title="❌ You don't have permission to send messages",
                description="You must have the required role to send messages in this channel.",
                color=discord.Color.red()
            )
            warning_message = await message.author.send(embed=warning_embed)

            # Delete the warning embed after 5 seconds
            await asyncio.sleep(5)
            await warning_message.delete()
            return  # Stop further processing

# Run the bot
bot.run("MTM3MDc3NzExNDMxMTI2MjMxOA.G27o-r.VDAE7xsAwqoxwANsCyRzvqknw0TNNyntFWR4eI")