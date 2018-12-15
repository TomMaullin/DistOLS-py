import glob
import numpy as np
import nibabel as nib
import os

def main():

    print('running')
    Y_files = glob.glob('/gpfs2/well/nichols/projects/UKB/MNI/*_tfMRI_cope1_MNI.nii.gz')
    os.mkdir(os.path.join(os.getcwd(),'BLM','test','data','ukbb'))

    j = 1
    for Y_file in Y_files:

        print('j: ' + str(j))

        for i in range(10, len(Y_files)+1):

            if j <= i:

                print('i: ' + str(i))

                with open(os.path.join(os.getcwd(),'BLM','test','data','ukbb', 'Y_files_ukbb_' + str(i) + '.txt'), 'a') as a:

                    a.write(Y_file + os.linesep)

            i = i+1

        j = j+1

    print('done')
        

if __name__ == "__main__":
    main()

