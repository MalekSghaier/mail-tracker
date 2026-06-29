import base64

PIXEL_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAA"
    "AAYAAjCB0C8AAAAASUVORK5CYII="
)

with open("pixel.png", "wb") as f:
    f.write(base64.b64decode(PIXEL_BASE64))

print("pixel.png créé.")