import time
import discord
from discord import app_commands
import json
import uuid

# Constants
DST_ROLE_ID = 1330291577607684107
EVOC_ROLE_ID = 1330291574814539786
PING_ROLE_ID = 1330291576202727567
INSTRUCTIONS_CHANNEL_ID = 1202417039893995651
TRAINING_LOG_FILE = "training_logs.json"

def load_training_logs():
    """Load training logs from the JSON file."""
    try:
        with open(TRAINING_LOG_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_training_logs(logs):
    """Save training logs to the JSON file."""
    with open(TRAINING_LOG_FILE, "w") as f:
        json.dump(logs, f, indent=4)

# Intents and bot setup
intents = discord.Intents.all()
intents.members = True  # Required to check user roles
intents.guilds = True
intents.message_content = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await tree.sync()
        print(f"✅ Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"❌ Sync error: {e}")

@tree.command(name="training", description="Log a LASD training session")
@app_commands.describe(
    available_time="When are you available?",
    group="Were you accepted into the group?"
)
async def training(
    interaction: discord.Interaction,
    available_time: str,
    group: bool
):
    user = interaction.user
    roles = [role.id for role in user.roles]
    training_type = "EVOC"  # Default training type
    accepted: bool
    accepted = False

    # Detect training type (DST or EVOC)
    if DST_ROLE_ID in roles:
        training_type = "DST"
    else:
        await interaction.response.send_message(
            "❌ You must have the DST role to use this command.",
            ephemeral=True
        )
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

    # Generate unique training ID
    training_id = str(uuid.uuid4())

    # Load existing training logs
    logs = load_training_logs()

    # Store new training entry
    logs[training_id] = {
        "username": user.name,
        "user_id": str(user.id),
        "training_type": training_type,
        "available_time": available_time,
        "group_status": group,
        "accepted": accepted
    }

    # Save updated logs to JSON
    save_training_logs(logs)

    # Send confirmation embed
    embed = discord.Embed(
        title="📋 LASD Training Log",
        description="This training entry has been successfully logged.",
        color=discord.Color.blue()
    )
    embed.add_field(name="👤 Username", value=user.mention, inline=True)
    embed.add_field(name="📘 Training Type", value=training_type, inline=True)
    embed.add_field(name="✅ Group Status", value="Yes", inline=True)
    embed.add_field(name="⏰ Available Time", value=available_time, inline=False)
    embed.add_field(name="🆔 Training ID", value=training_id, inline=False)  # New field for ID
    embed.set_footer(text="Submitted via /training", icon_url=user.display_avatar.url)
    
    channel = interaction.guild.get_channel(1330460907729322014)
    await channel.send(content=f"<@&{PING_ROLE_ID}>, <@{user.mention}>", allowed_mentions=discord.AllowedMentions(roles=True), embed=embed)
    await interaction.followup.send("✅ Your training has been sent! Please wait for it to be accepted", ephemeral=True)

@tree.command(name="training_accept", description="Accept a training submission by ID")
@app_commands.describe(
    training_id="Enter the training ID to accept."
)
async def training_accept(
    interaction: discord.Interaction,
    training_id: str
):
    # Check if the user has the required role to accept training
    if not any(role.id == 1330291576202727567 for role in interaction.user.roles):
        await interaction.response.send_message(
            "❌ You don't have permission to accept training submissions.",
            ephemeral=True
        )
        return

    # Load the existing training logs from the JSON file
    logs = load_training_logs()

    # Check if the training ID exists
    if training_id not in logs:
        await interaction.response.send_message(
            f"❌ No training log found for ID `{training_id}`.",
            ephemeral=True
        )
        return

    # Retrieve the training entry
    training_data = logs[training_id]

    # Check if it's already accepted
    if training_data['accepted'] == 'true':
        await interaction.response.send_message(
            f"❌ Training ID `{training_id}` has already been accepted.",
            ephemeral=True
        )
        return

    # Update the accepted status to True
    training_data['accepted'] = 'true'

    # Save the updated logs to the JSON file
    save_training_logs(logs)

    # Send confirmation embed
    embed = discord.Embed(
        title="✅ Training Accepted",
        description=f"Training with ID `{training_id}` has been accepted.",
        color=discord.Color.green()
    )
    embed.add_field(name="Traning accepted", value="Training acceptance confirmed.")

    # Send the embed to the channel
    await interaction.response.send_message(embed=embed, ephemeral=True)

    # Ping the user in the channel
    user_to_notify = await interaction.guild.fetch_member(int(training_data["user_id"]))
    if user_to_notify:
        # Send a direct message to the user with instructions
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

        # Ping the user in the channel
        embed = discord.Embed(
            title="🚨 Training Request Accepted!",
            description=(
                f"<@{training_data['user_id']}>, your training request has been **accepted**!\n\n"
                "📩 Please check your **DMs** for instructions on how to get ready for your session.\n"
                "Make sure to be prepared and on time!"
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text="LASD Training Unit")

        await channel.send(embed=embed)

    # If the user isn't found, send a warning
    else:
        await interaction.response.send_message(
            f"❌ The user with ID `{training_data['user_id']}` was not found or is not in the server.",
            ephemeral=True
        )


# Run the bot
bot.run("MTM3MDc3NzExNDMxMTI2MjMxOA.G27o-r.VDAE7xsAwqoxwANsCyRzvqknw0TNNyntFWR4eI")
