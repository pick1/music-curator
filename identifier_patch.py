import re

def _clean(text: str) -> str:
    """Clean extracted text."""
    text = text.strip()
    # Strip leading @ from handles but keep the name
    text = re.sub(r"@(\w+)", r"\1", text)
    # Remove trailing hashtags and URLs
    text = re.sub(r"\s*#\w+", "", text)
    text = re.sub(r"\s*https?://\S+", "", text)
    # Remove emojis
    text = re.sub(r"[🎵🎶🎧🔊🎤🎸🎹🎺🎻🥁🎷🎶]", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()

# Test with the actual caption
caption = "@weareoliver - Night Is On My Mind\non @foolsgoldrecs"
for line in caption.split("\n"):
    line = line.strip()
    # Match @handle - Track or plain artist - Track
    m = re.search(r"@?([^-\n@]+?)\s*-\s*([^\n]+)", line, re.IGNORECASE)
    if m:
        artist = _clean(m.group(1))
        track = _clean(m.group(2))
        print(f"Artist: {artist!r}  Track: {track!r}")
        break
