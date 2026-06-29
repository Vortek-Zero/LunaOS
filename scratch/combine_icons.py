from PIL import Image

def combine():
    # Load background and foreground logo
    bg = Image.open('/home/pera/Luna/newlogoluna.png')
    fg = Image.open('/home/pera/Luna/newlogoluna.png')

    # Get bounding box of the logo to remove empty transparency around it
    bbox = fg.getbbox()
    if bbox:
        fg_cropped = fg.crop(bbox)
    else:
        fg_cropped = fg

    # We want the logo to occupy about 60% of the background's width
    target_width = int(bg.width * 0.6)
    aspect_ratio = fg_cropped.height / fg_cropped.width
    target_height = int(target_width * aspect_ratio)

    # Resize cropped logo
    fg_resized = fg_cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)

    # Create a copy of the background to paste on
    combined = bg.copy()

    # Calculate center position
    x = (combined.width - fg_resized.width) // 2
    y = (combined.height - fg_resized.height) // 2

    # Paste using the alpha channel of the resized logo as the mask
    combined.paste(fg_resized, (x, y), fg_resized)

    # Save the output
    output_path = '/home/pera/Luna/luna-desktop/src-tauri/icons/icon.png'
    combined.save(output_path, 'PNG')
    print(f"Icon generated and saved to {output_path}")

if __name__ == '__main__':
    combine()
