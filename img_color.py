'''
    Created 3-14-22.  Find the dominant colors of images in a directory.  Find the image 
    with the dominant color closest to the user selected color.

    Dominant colors found by k-means clustering following user Tonechas at:
    https://stackoverflow.com/questions/43111029/how-to-find-the-average-colour-of-an-image-in-python-with-opencv
'''


# GUI
import tkinter as tk
from tkinter.colorchooser import askcolor
from tkinter import filedialog
# Plotting
import matplotlib
# Necessary to get pyplot and tk to play well.
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import math
# Image processing
import numpy as np
import cv2
from skimage import io
from skimage import color
# Working with paths, file names, directories
from pathlib import Path, PureWindowsPath
import os

class Picture(): 
    def __init__(self, path=None, stats=None):
        if path and stats: 
            raise ValueError("Instantiate a Picture with either a stats file or a path, not both.")
        elif not path and not stats:
            raise ValueError("A Picture must be instantiated with either a path or stats file.  Neither was provided.")

        if stats:
            # If there is an .npz of existing image data, use it to populate the Picture's computed properties.
            stats = np.load(stats)
            self.path = Path(stats['path'][0])
            self.palette = stats['palette']
            self.counts = stats['counts']
            self.dominant = stats['dominant']
            self.make_image()
        else: 
            self.path = path
            self.make_image()
            self.cluster()
    
    def make_image(self): 
        # Tonechas used slice [:, :, :-1] to ignore the alpha channel. I am instead converting rgba to rgb if necessary.  
        self.img = io.imread(self.path)[:, :, :]
        if self.img.shape[2] == 4: 
            # If the image is rgba, convert it.
            self.img = color.rgba2rgb(self.img)

    def __repr__(self):
        # Stop numpy printing in scientific notation, see https://stackoverflow.com/questions/9777783/suppress-scientific-notation-in-numpy-when-creating-array-from-nested-list
        np.set_printoptions(suppress=True)
        return ' ; '.join([
            # This exports the path string with forward slashes, which avoids errors later with another Path is instantiated with the string.
            self.path.as_posix(),
            # The center of the largest color cluster
            np.array2string(self.dominant, precision=3, floatmode='fixed', max_line_width=None, separator=',').replace('\n', '').replace(' ', '')])

    def export_stats(self, filename):
        '''
            Save a .npz file (a platform agnostic archive of several numpy arrays) of computed image stats.
        '''
        np.savez(
            filename, 
            path=np.array([self.path]).astype(str),
            counts=self.counts, 
            palette=self.palette, 
            dominant=self.dominant)

    def cluster(self, n_colors=5): 
        '''
            Perform k-means clustering on the image to determine its dominant colors.
        '''
        pixels = np.float32(self.img.reshape(-1,3))
        self.n_colors = n_colors
        # The first component of the criteria tuple specifies the termination criterion:
        # "stop when either the given error epsilon or the max iterations is reached."
        # The second component is the max iteration count; the third is the error epsilon.
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, .1)
        # How the initial centers are chosen
        flags = cv2.KMEANS_RANDOM_CENTERS

        # palette gives the chosen cluster centers
        _, labels, self.palette = cv2.kmeans(pixels, self.n_colors, None, criteria, 5, flags)
        # counts gives the size of each cluster. Order is the same as the order of centers in self.palette.
        _, self.counts = np.unique(labels, return_counts=True)
        self.dominant = self.palette[np.argmax(self.counts)]

    def get_distance_to(self, other): 
        '''
            Return the Euclidean distance from the image's color center which is closest to the user input color. 
            'other' should be a list-like RGB value, ie (233, 0, 1.2)
        '''
        return min([np.linalg.norm(color - np.float32(other)) for color in self.palette])

    def plot_palette(self, ax):
        '''
            Passed a subplot, create with it a stack of the dominant colors
            with layer
        '''
        indices = np.argsort(self.counts)[::-1]
        freqs = np.cumsum(np.hstack([[0], self.counts[indices]/float(self.counts.sum())]))
        rows = np.int_(self.img.shape[0]*freqs)

        dom_patch = np.zeros(shape=self.img.shape, dtype=np.uint8)
        for i in range(len(rows) - 1): 
            dom_patch[rows[i]:rows[i+1], :, :] += np.uint8(self.palette[indices[i]])

        ax.imshow(dom_patch)
        ax.axis('off')
        ax.set_title(str(self.path.name))

class Collection():
    def __init__(self, choose_dir=False, picture_folder='gui pictures/'): 
        # picture_folder should be a directory which contains only image files.
        if choose_dir:
            # Stop an empty root window from appearing
            tk.Tk().withdraw()
            picture_folder = filedialog.askdirectory()
        self.picture_folder = Path(picture_folder)

        self.data_dir = self.picture_folder / 'pic_stats'
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.pictures = []

        # Sets of picture and data files in the main and data directories, respectively.
        extensions = {'.png', '.jpg', '.PNG', '.JPG'} 
        # Include only png and jpg files in the main directory.
        pic_set = {path for path in filter(lambda path: path.is_file() and path.suffix in extensions, self.picture_folder.glob('**/*'))}
        data_set = {path for path in self.data_dir.glob('**/*.npz')}
        # Just the filenames of the above sets, with the paths and extensions stripped away, for faster searching below.
        pic_names = {path.with_suffix('').name for path in pic_set}
        data_names = {path.with_suffix('').name for path in data_set}

        for pic in pic_set: 
            if pic.with_suffix('').name in data_names: 
                # If a picture and its data exist, create the Picture object from the data file.
                self.pictures.append(Picture(stats = (self.data_dir / pic.with_suffix('').name).with_suffix('.npz')))
            else: 
                # If there is a picture without data, create the Picture object, compute the data, and save it to a file.
                self.pictures.append(Picture(path = pic))
                # np.savez (in Picture.export_stats) will append the .npz extension
                self.pictures[-1].export_stats((self.data_dir / pic.with_suffix('').name).as_posix())

        for name in data_names.difference(pic_names): 
            # Delete data files for missing pictures.
            (self.data_dir / name).with_suffix(".npz").unlink


    def get_closest(self):
        # Use tkinter color widget to get a color from the user
        color = askcolor()[0]
        min_distance = 1e9
        closest = None

        for picture in self.pictures:
            distance = picture.get_distance_to(color)
            if distance < min_distance:
                min_distance = distance
                closest = picture
        os.startfile(closest.path)
        return closest.path

    def plot_palettes(self):
        plot_count = len(self.pictures)
        # The smallest square grid with at least plot_count cells
        col_count = math.ceil(plot_count ** (1 / 2))
        row_count = col_count
        # Remove empty subplot rows
        while (row_count - 1) * col_count >= plot_count:
            row_count -= 1
        # axs is a row_count by col_count array of subplots.  
        fig, axs = plt.subplots(row_count, col_count)

        for index, picture in enumerate(self.pictures):
            row = index // col_count
            col = index % col_count
            picture.plot_palette(axs[row, col])
        
        plt.show()

if __name__ == '__main__':
    collection = Collection(True)
    for picture in collection.pictures:
        print(picture)
    collection.plot_palettes()
    while True: 
        # Open the image with the closest color
        collection.get_closest()