import discord


# 0 - precuts have not been indexed
# 1 - precuts have been indexed
async def leaderboard_embed(client, rows):
    embed = discord.Embed(
        title="🏆 Precut Leaderboard",
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

        hours = int(duration // 3600)
        minutes = int((duration % 3600) // 60)
        seconds = int(duration % 60)

        mention = user.mention if user else f"<@{author_id}>"
        embed.description += (
            f"**{i}.** {mention}\n"
            f"📹 {count} precuts • ⏱️ {hours}h {minutes}m {seconds}s\n\n"
        )

    return embed, 1
