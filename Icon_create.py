from PIL import Image

img = Image.open("Aries.jpg")

img.save("Aries.ico", format="ICO", sizes=[(256, 256)])
