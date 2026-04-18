#!/usr/bin/env python3

import argparse
import json
import os
import PIL.Image
import PIL.ImageChops
import sys

########################################
# Species ##############################
########################################

g_kemono_database = 'kemono.json'
g_translucency_threshold = 6

########################################
# Functions ############################
########################################

def image_sizes_equal(lhs, rhs):
    """Checks if image sizes are equal."""
    return (lhs.width == rhs.width) and (lhs.height == rhs.height)

def image_modes_equal(lhs, rhs):
    """Checks if image modes are equal."""
    return lhs.mode == rhs.mode

def image_channels_equal(lhs, rhs, channel):
    """Checks if given channels within images are equal."""
    if (not image_sizes_equal(lhs, rhs)) or (not image_modes_equal(lhs, rhs)):
        raise RuntimeError("image_channels_equal(): image sizes and modes must be equal")
    lhs_data = lhs.get_flattened_data()
    rhs_data = rhs.get_flattened_data()
    for ii in range(len(lhs_data)):
        lhs_pixel = lhs_data[ii]
        rhs_pixel = rhs_data[ii]
        if lhs_pixel[channel] != rhs_pixel[channel]:
            return False
    return True

def images_equal(lhs, rhs):
    """Checks if given images are equal."""
    if (not image_sizes_equal(lhs, rhs)) or (not image_modes_equal(lhs, rhs)):
        return False
    if lhs.mode == "RGBA":
        if not image_channels_equal(lhs, rhs, 3):
            return False
        diff = PIL.ImageChops.difference(lhs.convert("RGB"), rhs.convert("RGB"))
    elif lhs.mode == "RGB":
        diff = PIL.ImageChops.difference(lhs, rhs)
    else:
        raise RuntimeError("image_equals(): unsupported mode '%s'", (lhs.mode))
    if not diff.getbbox():
        return True
    return False

def image_create_empty_rgba(sx, sy):
    """Creates a new fully transparent image."""
    return PIL.Image.new(mode='RGBA', size=(sx, sy), color=(0, 0, 0, 0))

def image_paste_center(dst, src):
    """Pastes source image to the center of destination image."""
    tx = round(float(dst.width - src.width) / 2.0)
    ty = round(float(dst.height - src.height) / 2.0)
    dst.paste(src, (tx, ty))

def image_transparent_to_transparent_black(img):
    """Converts all fully transparent pixels in image to transparent black."""
    if img.mode != "RGBA":
        raise RuntimeError("invalid image mode: '%s'" % (img.mode))
    ret = False
    pixels = img.load()
    for ii in range(img.width):
        for jj in range(img.height):
            pixel = img.getpixel((ii, jj))
            # Simple case.
            if pixel[3] <= g_translucency_threshold:
                pixels[ii, jj] = (0, 0, 0, 0)
                ret = True
    return ret

def image_crop_content(img, border_lr = None, border_ud = None):
    """Crop image to the actual content, add border if missing."""
    if (border_lr is None) and (border_ud is None):
        return img
    # Erase essentially translucent areas completely before calculating bounding box.
    image_transparent_to_transparent_black(img)
    for ii in img.get_flattened_data():
        if (ii[3] == 0) and ((ii[0] + ii[1] + ii[2]) > 0):
            raise RuntimeError("lol: %s" % (str(ii)))
    bbox = img.getbbox()
    if not bbox:
        raise RuntimeError("image_crop_content(): no content")
    if border_lr is None:
        bbox = (0, bbox[1], img.width, bbox[3])
    if border_ud is None:
        bbox = (bbox[0], 0, bbox[2], img.height)
    img = img.crop(bbox)
    tgt_width = img.width
    tgt_height = img.height
    if not (border_lr is None):
        tgt_width += 2 * border_lr
    if not (border_ud is None):
        tgt_height += 2 * border_ud
    cropped_image = image_create_empty_rgba(tgt_width, tgt_height)
    image_paste_center(cropped_image, img)
    return cropped_image

########################################
# Species ##############################
########################################

class Portrait:
    """Class abstracting a species portrait."""

    def __init__(self, name, scale = None, offset = None):
        """Constructor."""
        self.__name = name
        self.__scale = scale
        self.__offset = offset

    def generateImage(self, infile, outfile, target_height):
        """Generates image."""
        img = PIL.Image.open(infile)
        img = image_crop_content(img, 4, 4)
        factor = float(target_height) * self.__scale / float(img.size[1])
        tx = int(factor * img.size[0])
        ty = int(factor * img.size[1])
        scaled_img = img.resize((tx, ty), PIL.Image.Resampling.LANCZOS)
        dst_image = image_create_empty_rgba(tx, target_height)
        dy = int(self.__offset * float(target_height))
        dst_image.paste(scaled_img, (0, dy))
        dst_image = image_crop_content(dst_image, 2)
        try:
            cmp_image = PIL.Image.open(outfile)
            if images_equal(dst_image, cmp_image):
                print("Image: '%s' (%ix%i) not changed" % (outfile, tx, target_height))
            else:
                dst_image.save(outfile)
                print("Image: '%s' (%ix%i) updated" % (outfile, tx, target_height))
        except FileNotFoundError:
            dst_image.save(outfile)
            print("Image: '%s' (%ix%i) created" % (outfile, tx, target_height))

    def getName(self):
        """Accessor."""
        return self.__name

########################################
# SpeciesDB ############################
########################################

class PortraitDB:
    """Portrait database."""

    def __init__(self):
        """Constructor."""
        self.readFromJson(g_kemono_database)

    def generateImages(self):
        """Updates all images."""
        for ii in self.__portraits:
            fileName = ii.getName() + ".png"
            dstFile = os.path.join(self.__dst_directory, ii.getName() + ".png")
            srcFile = os.path.join(self.__src_directory, fileName)
            ii.generateImage(srcFile, dstFile, self.__target_height)

    def readFromJson(self, op):
        """Reads data from json."""
        if not os.path.isfile(op):
            raise RuntimeError("database not found: '%s'" % (op))
        fd = open(op, 'r')
        data = json.load(fd)
        fd.close()
        self.__dst_directory = data['dst_directory']
        self.__src_directory = data['src_directory']
        self.__target_height = int(data['target_height'])
        self.__portraits = []
        for ii in data['portraits']:
            name = ii['name']
            for jj in self.__portraits:
                if jj.getName() == name:
                    raise RuntimeError("readFromJson(): multiple instances of portrait '%s'" % (name))
            scale = float(ii['scale'])
            offset = float(ii['offset'])
            self.__portraits += [Portrait(name, scale, offset)]

    def verify(self):
        """Verifies data against existing files."""

########################################
# __main__ #############################
########################################

if __name__ == '__main__':

    program_name = os.path.basename(sys.argv[0])

    parser = argparse.ArgumentParser(usage="%s [options]" % (program_name), add_help=False, formatter_class=argparse.RawDescriptionHelpFormatter, description="""Script for regenerating mod images.""")
    parser.add_argument("-h", "--help", action="store_true", help="Print this help message and exit")
    parser.add_argument("--verify", action="store_true", help="Verify portraits and the database match")

    args = parser.parse_args()

    if args.help:
        parser.print_help(sys.stdout)
        sys.exit(0)

    if args.verify:
        raise RuntimeError('not implemented yet')

    # Execution is relevant to script path.
    script_path = os.path.abspath(os.path.dirname(__file__))
    current_path = os.path.abspath(os.getcwd())
    if script_path != current_path:
        print("Executing from script directory: '%s'" % (os.path.relpath(script_path, current_path)))
        os.chdir(script_path)

    db = PortraitDB()
    db.generateImages()

    sys.exit(0)
