import time
import discord
from discord import app_commands
import json
import uuid
import logging
import os
import sys
from datetime import datetime

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

intents = discord.Intents.all()
intents.members = True
intents.guilds = True
intents.message_content = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user}")
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
    training_type = "EVOC"
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
            description=(
                "You must be **accepted into the group** to submit a training log.\n\n"
                f"📌 Please review the steps in <#{INSTRUCTIONS_CHANNEL_ID}> before proceeding."
            ),
            color=discord.Color.red()
        )
        embed.set_footer(text="Please contact staff for assistance.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    training_id = str(uuid.uuid4())
    logs = load_training_logs()

    logs[training_id] = {
        "username": user.name,
        "user_id": str(user.id),
        "training_type": training_type,
        "available_time": available_time,
        "group_status": group,
        "accepted": accepted
    }

    save_training_logs(logs)
    logging.info(f"New training logged: {training_id} by {user}")

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
    await channel.send(content=f"<@&{PING_ROLE_ID}>, <@{user.mention}>", allowed_mentions=discord.AllowedMentions(roles=True), embed=embed)
    await interaction.followup.send("✅ Your training has been sent! Please wait for it to be accepted", ephemeral=True)

@tree.command(name="training_accept", description="Accept a training submission by ID")
@app_commands.describe(training_id="Enter the training ID to accept.")
async def training_accept(interaction: discord.Interaction, training_id: str):
    if not any(role.id == 1330291576202727567 for role in interaction.user.roles):
        await interaction.response.send_message("❌ You don't have permission to accept training submissions.", ephemeral=True)
        logging.warning(f"{interaction.user} tried to accept a training without permission.")
        return

    logs = load_training_logs()
    if training_id not in logs:
        await interaction.response.send_message(f"❌ No training log found for ID `{training_id}`.", ephemeral=True)
        logging.warning(f"Training ID not found: {training_id}")
        return

    training_data = logs[training_id]
    if training_data['accepted'] == 'true':
        await interaction.response.send_message(f"❌ Training ID `{training_id}` has already been accepted.", ephemeral=True)
        return

    training_data['accepted'] = 'true'
    save_training_logs(logs)

    logging.info(f"Training ID {training_id} accepted by {interaction.user}")

    embed = discord.Embed(
        title="✅ Training Accepted",
        description=f"Training with ID `{training_id}` has been accepted.",
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
                "• **Join the briefing room** 🏢\n"
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
        await interaction.response.send_message(f"❌ The user with ID `{training_data['user_id']}` was not found or is not in the server.", ephemeral=True)

@tree.command(name="restart", description="Restart the bot (Admin only)")
async def restart(interaction: discord.Interaction):
    if interaction.user.id != YOUR_DISCORD_USER_ID:
        await interaction.response.send_message("❌ You don't have permission to restart the bot.", ephemeral=True)
        logging.warning(f"Unauthorized restart attempt by {interaction.user}")
        return

    # Save info for restart confirmation
    with open(RESTART_INFO_FILE, "w") as f:
        json.dump({
            "user_id": interaction.user.id,
            "channel_id": interaction.channel.id
        }, f)

    await interaction.response.send_message("♻️ Restarting bot...", ephemeral=False)
    logging.info(f"Bot restart initiated by {interaction.user}")
    await bot.close()
    os.execv(sys.executable, [sys.executable] + sys.argv)

# Run the bot
bot.run("MTM3MDc3NzExNDMxMTI2MjMxOA.G27o-r.VDAE7xsAwqoxwANsCyRzvqknw0TNNyntFWR4eI")
