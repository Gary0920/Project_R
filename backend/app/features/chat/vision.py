from __future__ import annotations


def attach_vision_images_to_latest_user_message(
    messages: list[dict],
    images: list[dict[str, str]],
    provider: str,
) -> list[dict]:
    updated = [dict(message) for message in messages]
    for index in range(len(updated) - 1, -1, -1):
        if updated[index].get("role") != "user":
            continue
        content = updated[index].get("content", "")
        text = content if isinstance(content, str) else ""
        updated[index]["content"] = build_vision_content_blocks(text, images, provider)
        break
    return updated


def build_vision_content_blocks(
    text: str,
    images: list[dict[str, str]],
    provider: str,
) -> list[dict]:
    blocks: list[dict] = []
    if text:
        blocks.append({"type": "text", "text": text})
    if provider == "claude":
        blocks.extend(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image["media_type"],
                    "data": image["data"],
                },
            }
            for image in images
        )
    else:
        blocks.extend(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{image['media_type']};base64,{image['data']}"},
            }
            for image in images
        )
    return blocks
