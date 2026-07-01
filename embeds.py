import discord

from database import get_time


# 0 - precuts have not been indexed
# 1 - precuts have been indexed
async def leaderboard_embed(client: discord.Client, rows, board_type: str):
    embed = discord.Embed(
        title=f"🏆 {board_type} Precut Leaderboard",
        colour=discord.Colour.gold(),
    )

    if not rows:
        embed.description = "No precuts have been indexed yet."
        return embed, 0

    embed.description = ""
    for i, (author_id, count, duration) in enumerate(rows, start=1):
        user = client.get_user(author_id)

        if user is None:
            try:
                user = await client.fetch_user(author_id)
            except discord.NotFound:
                username = f"Unknown User ({author_id})"
            else:
                username = user.display_name
        else:
            username = user.display_name

        hours, minutes, seconds = get_time(duration)
        mention = user.mention if user else f"<@{author_id}>"
        embed.description += (
            f"**{i}.** {mention}\n"
            f"📹 {count} precuts  ⏱️ {hours}h {minutes}m {seconds}s\n\n"
        )

    return embed, 1


async def stats_embed(
    client: discord.Client,
    stats,
    user: discord.User,
):
    embed = discord.Embed(
        title=f"{user.display_name}'s Precut Stats",
        colour=discord.Colour.blurple(),
    )

    embed.set_thumbnail(url=user.display_avatar.url)

    if stats is None:
        embed.description = "No precuts have been donated yet BUM."
        return embed

    owner_id, precut_count, duration, rank = stats

    duration = duration or 0
    hours, minutes, seconds = get_time(duration)

    embed.add_field(
        name="🏆 Leaderboard Position",
        value=f"#{rank}",
        inline=False,
    )

    embed.add_field(
        name="📹 Total Precuts",
        value=str(precut_count),
        inline=True,
    )

    embed.add_field(
        name="⏱️ Total Duration",
        value=f"{hours}h {minutes}m {seconds}s",
        inline=True,
    )

    return embed
