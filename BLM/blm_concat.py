import warnings as w
# This warning is caused by numpy updates and should
# be ignored for now.
w.simplefilter(action = 'ignore', category = FutureWarning)
import numpy as np
import subprocess
import warnings
import resource
import nibabel as nib
import sys
import os
import glob
import shutil
import yaml
import pandas
import time
import warnings
import subprocess
np.set_printoptions(threshold=np.nan)

def main(*args):

    # ----------------------------------------------------------------------
    # Check inputs
    # ----------------------------------------------------------------------
    if len(args)==0:
        # Load in inputs
        with open(os.path.join(
                    os.path.dirname(os.path.realpath(__file__)),
                    '..',
                    'blm_defaults.yml'), 'r') as stream:
            inputs = yaml.load(stream)
    else:
        # In this case inputs is first argument
        inputs = args[0]

    # ----------------------------------------------------------------------
    # Read basic inputs
    # ----------------------------------------------------------------------
    OutDir = inputs['outdir']
    
    # Get number of parameters
    c1 = blm_eval(inputs['contrasts'][0]['c' + str(1)]['vector'])
    c1 = np.array(c1)
    n_p = c1.shape[0]
    del c1
    
    # Read in the nifti size and work out number of voxels.
    with open(inputs['Y_files']) as a:
        nifti_path = a.readline().replace('\n', '')
        nifti = nib.load(nifti_path)

    NIFTIsize = nifti.shape
    n_v = int(np.prod(NIFTIsize))

    # ----------------------------------------------------------------------
    # Load X'X, X'Y, Y'Y and n_s
    # ----------------------------------------------------------------------
    if len(args)==0:
        # Read the matrices from the first batch. Note XtY is transposed as pandas
        # handles lots of rows much faster than lots of columns.
        sumXtX = pandas.io.parsers.read_csv(os.path.join(OutDir,"tmp","XtX1.csv"), 
                            sep=",", header=None).values
        sumXtY = pandas.io.parsers.read_csv(os.path.join(OutDir,"tmp","XtY1.csv"), 
                            sep=",", header=None).values.transpose()
        sumYtY = pandas.io.parsers.read_csv(os.path.join(OutDir,"tmp","YtY1.csv"), 
                            sep=",", header=None).values
        nmapb  = nib.load(os.path.join(OutDir,"tmp", "blm_vox_n_batch1.nii"))
        n_s_sv = nmapb.get_data()

        # Delete the files as they are no longer needed.
        os.remove(os.path.join(OutDir,"tmp","XtX1.csv"))
        os.remove(os.path.join(OutDir,"tmp","XtY1.csv"))
        os.remove(os.path.join(OutDir,"tmp","YtY1.csv"))
        os.remove(os.path.join(OutDir,"tmp","blm_vox_n_batch1.nii"))

        # Work out how many files we need.
        XtX_files = glob.glob(os.path.join(OutDir,"tmp","XtX*"))

        # Cycle through batches and add together results.
        for batchNo in range(2,(len(XtX_files)+2)):

            # Sum the batches.
            sumXtX = sumXtX + pandas.io.parsers.read_csv(
                os.path.join(OutDir,"tmp","XtX" + str(batchNo) + ".csv"), 
                             sep=",", header=None).values

            sumXtY = sumXtY + pandas.io.parsers.read_csv(
                os.path.join(OutDir,"tmp","XtY" + str(batchNo) + ".csv"), 
                             sep=",", header=None).values.transpose()

            sumYtY = sumYtY + pandas.io.parsers.read_csv(
                os.path.join(OutDir,"tmp","YtY" + str(batchNo) + ".csv"), 
                             sep=",", header=None).values
            
            # Obtain the full nmap.
            n_s_sv = n_s_sv + nib.load(os.path.join(OutDir,"tmp", 
                "blm_vox_n_batch" + str(batchNo) + ".nii")).get_data()
            
            # Delete the files as they are no longer needed.
            os.remove(os.path.join(OutDir, "tmp","XtX" + str(batchNo) + ".csv"))
            os.remove(os.path.join(OutDir, "tmp","XtY" + str(batchNo) + ".csv"))
            os.remove(os.path.join(OutDir, "tmp","YtY" + str(batchNo) + ".csv"))
            os.remove(os.path.join(OutDir, "tmp", "blm_vox_n_batch" + str(batchNo) + ".nii"))

    else:
        # Read in sums.
        sumXtX = args[1]
        sumXtY = args[2].transpose()
        sumYtY = args[3]
        n_s_sv = args[4]

    # Save nmap
    nmap = nib.Nifti1Image(n_s_sv,
                           nifti.affine,
                           header=nifti.header)
    nib.save(nmap, os.path.join(OutDir,'blm_vox_n.nii'))

    # Dimension bug handling
    if np.ndim(sumXtX) == 0:
        sumXtX = np.array([[sumXtX]])
    elif np.ndim(sumXtX) == 1:
        sumXtX = np.array([sumXtX])

    if np.ndim(sumXtY) == 0:
        sumXtY = np.array([[sumXtY]])
    elif np.ndim(sumXtY) == 1:
        sumXtY = np.array([sumXtY])

    # Get ns.
    X = pandas.io.parsers.read_csv(
        inputs['X'], sep=',', header=None).values
    n_s = X.shape[0]

    # ----------------------------------------------------------------------
    # Create Mask
    # ----------------------------------------------------------------------

    Mask = np.ones([n_v, 1])

    # Apply user specified missingness thresholding.
    if ("Relative" in inputs["Missingness"]) or ("relative" in inputs["Missingness"]):

        # Read in relative threshold
        if "Relative" in inputs["Missingness"]:
            rmThresh = inputs["Missingness"]["Relative"]
        else:
            rmThresh = inputs["Missingness"]["relative"]

        # If it's a percentage it will be a string and must be converted.
        rmThresh = str(rmThresh)
        if "%" in rmThresh:
            rmThresh = float(rmThresh.replace("%", ""))/100
        else:
            rmThresh = float(rmThresh)

        # Check the Relative threshold is between 0 and 1.
        if (rmThresh < 0) or (rmThresh > 1):
            raise ValueError('Relative Missingness threshold is out of range: ' +
                             '0 < ' + str(rmThresh) + ' < 1 violation')

        # Mask based on threshold.
        Mask[n_s_sv.reshape(n_v, 1)<rmThresh*n_s]=0

    if ("Absolute" in inputs["Missingness"]) or ("absolute" in inputs["Missingness"]):

        # Read in relative threshold
        if "Absolute" in inputs["Missingness"]:
            amThresh = inputs["Missingness"]["Absolute"]
        else:
            amThresh = inputs["Missingness"]["absolute"]

        # If it's a percentage it will be a string and must be converted.
        if isinstance(amThresh, str):
            amThresh = float(amThresh)

        # Mask based on threshold.
        Mask[n_s_sv.reshape(n_v, 1)<amThresh]=0

    if ("Masking" in inputs["Missingness"]) or ("masking" in inputs["Missingness"]):

        # Read in threshold mask
        if "Masking" in inputs["Missingness"]:
            mmThresh_path = inputs["Missingness"]["Masking"]
        else:
            mmThresh_path = inputs["Missingness"]["masking"]

        try:
            # Read in the mask nifti.
            mmThresh = nib.load(mmThresh_path)

            # Check whether the mask has the same shape as the other niftis
            if np.array_equal(mmThresh.shape, NIFTIsize):
                mmThresh = mmThresh.get_data().reshape([n_v, 1])
            else:
                # Make flirt resample command
                resamplecmd = ["flirt", "-in", mmThresh_path,
                                        "-ref", nifti_path,
                                        "-out", os.path.join(OutDir, 'tmp', 'blm_im_resized.nii'),
                                        "-applyxfm"]

                # Warn the user about what is happening.
                warnings.warn('Masking NIFTI ' + mmThresh_path + ' does not have the'\
                              ' same dimensions as the input data and will therefore'\
                              ' be resampled using FLIRT.')

                # Run the command
                process = subprocess.Popen(resamplecmd, shell=False,
                                           stdout=subprocess.PIPE)
                out, err = process.communicate()

                # Check the NIFTI has been generate, else wait up to 5 minutes.
                t = time.time()
                t1 = 0
                while (not os.path.isfile(os.path.join(OutDir, 'tmp', 'blm_im_resized.nii.gz'))) and (t1 < 300):
                    t1 = time.time() - t

                # Load the newly resized nifti mask
                mmThresh = nib.load(os.path.join(OutDir, 'tmp', 'blm_im_resized.nii.gz'))

                mmThresh = mmThresh.get_data().reshape([n_v, 1])

        except:
            raise ValueError('Nifti image ' + mmThresh_path + ' will not load.')

        # Apply mask nifti.
        Mask[mmThresh==0]=0


    # We remove anything with 1 degree of freedom (or less) by default.
    # 1 degree of freedom seems to cause broadcasting errors on a very
    # small percentage of voxels.
    Mask[n_s_sv.reshape(n_v, 1)<=n_p+1]=0

    # Reshape sumXtX to correct n_v by n_p by n_p
    sumXtX = sumXtX.reshape([n_v, n_p, n_p])

    # We also remove all voxels where the design has a column of just
    # zeros.
    for i in range(0,n_p):
        Mask[np.where(sumXtX[:,i,i]==0)]=0

    # Remove voxels with designs without full rank.
    M_inds = np.where(Mask==1)[0]
    Mask[M_inds[np.where(
        np.absolute(blm_det(sumXtX[M_inds,:,:])) < np.sqrt(sys.float_info.epsilon)
        )]]=0

    # Output final mask map
    maskmap = nib.Nifti1Image(Mask.reshape(
                                    NIFTIsize[0],
                                    NIFTIsize[1],
                                    NIFTIsize[2]
                                    ),
                              nifti.affine,
                              header=nifti.header)
    nib.save(maskmap, os.path.join(OutDir,'blm_vox_mask.nii'))

    # Get indices of voxels in mask.
    M_inds = np.where(Mask==1)[0]

    # Number of voxels in mask
    n_v_m = M_inds.shape[0]

    # ----------------------------------------------------------------------
    # Calculate betahat = (X'X)^(-1)X'Y and output beta maps
    # ----------------------------------------------------------------------    

    # Calculate masked X'X
    sumXtX_m = sumXtX[M_inds,:,:]

    # Calculate masked X'Y
    sumXtY = sumXtY.transpose()
    sumXtY = sumXtY.reshape([n_v, n_p, 1])
    sumXtY_m = sumXtY[M_inds,:]

    # Calculate masked Beta
    beta_m = np.linalg.solve(sumXtX_m, sumXtY_m)

    # Unmask Beta
    beta = np.zeros([n_v, n_p])
    beta[M_inds,:] = beta_m.reshape([n_v_m, n_p])
    beta = beta.reshape([n_v, n_p]).transpose()


    # Cycle through betas and output results.
    for i in range(0,beta.shape[0]):

        betai = beta[i,:].reshape(int(NIFTIsize[0]),
                                  int(NIFTIsize[1]),
                                  int(NIFTIsize[2]))

        # Save beta map.
        betaimap = nib.Nifti1Image(betai,
                                   nifti.affine,
                                   header=nifti.header)
        nib.save(betaimap, os.path.join(OutDir,'blm_vox_beta_b' + str(i+1) + '.nii'))

    del betai, betaimap

    if np.ndim(beta) == 0:
        beta = np.array([[beta]])
    elif np.ndim(beta) == 1:
        beta = np.array([beta])

    # ----------------------------------------------------------------------
    # Calculate residual sum of squares e'e = Y'Y - (Xb)'Xb
    # ---------------------------------------------------------------------- 

    # Reshape beta along smallest axis for quicker
    # residual calculation
    beta_rs = np.zeros([n_v, n_p, 1])
    beta_rs_t = np.zeros([n_v, 1, n_p])
    for i in range(0,beta.shape[0]):

       beta_rs[:, i, 0] = beta[i,:]
       beta_rs_t[:, 0, i] = beta[i,:]

    # Calculate Beta transpose times XtX and delete the
    # now redudundant matrices.
    betatXtX = np.matmul(beta_rs_t, sumXtX)
    del beta_rs_t

    # Multiply BetatXtX by Beta and delete the reduundant
    # matrices.
    betatXtXbeta = np.matmul(betatXtX, beta_rs)
    del betatXtX, beta_rs

    # Reshape betat XtX beta
    betatXtXbeta = np.reshape(betatXtXbeta, [n_v,1])

    # Residual sum of squares
    ete_m = sumYtY[M_inds] - betatXtXbeta[M_inds]

    # Unmask ete
    ete = np.zeros([n_v, 1])
    ete[M_inds]=ete_m
    ete = ete.reshape(int(NIFTIsize[0]),
                      int(NIFTIsize[1]),
                      int(NIFTIsize[2]))

    # ----------------------------------------------------------------------
    # Calculate residual mean squares = e'e/(n_s - n_p)
    # ----------------------------------------------------------------------

    # Mask spatially varying n_s
    n_s_sv_m = n_s_sv.reshape(n_v, 1)
    n_s_sv_m = n_s_sv_m[M_inds,:]

    # Mask ete
    ete_m = ete.reshape(n_v, 1)
    ete_m = ete_m[M_inds,:]

    # In spatially varying the degrees of freedom
    # varies across voxels
    resms_m = ete_m/(n_s_sv_m-n_p)

    # Unmask resms
    resms = np.zeros([n_v,1])
    resms[M_inds,:] = resms_m
    resms = resms.reshape(NIFTIsize[0], 
                          NIFTIsize[1],
                          NIFTIsize[2])

    # Output ResSS.
    msmap = nib.Nifti1Image(resms,
                            nifti.affine,
                            header=nifti.header)
    nib.save(msmap, os.path.join(OutDir,'blm_vox_resms.nii'))

    # ----------------------------------------------------------------------
    # Calculate beta covariance maps
    # ----------------------------------------------------------------------
        
    # Calculate masked (x'X)^(-1) values
    sumXtX_m = sumXtX[M_inds,:,:]
    isumXtX_m = blm_inverse(sumXtX_m, ouflow=True).reshape([n_v_m, n_p*n_p])

    # Make (X'X)^(-1) unmasked
    isumXtX = np.zeros([n_v, n_p*n_p])
    isumXtX[M_inds,:]=isumXtX_m
    isumXtX = isumXtX.reshape([n_v, n_p, n_p])

    # Output variance for each pair of betas
    for i in range(0,n_p):
        for j in range(0,n_p):

                covbetaij = np.multiply(resms,
                    isumXtX[:,i,j].reshape(
                        NIFTIsize[0],
                        NIFTIsize[1],
                        NIFTIsize[2],
                        ))
                    
                # Output covariance map
                covbetaijmap = nib.Nifti1Image(covbetaij,
                                               nifti.affine,
                                               header=nifti.header)
                nib.save(covbetaijmap,
                    os.path.join(OutDir, 
                        'blm_vox_cov_b' + str(i+1) + ',' + str(j+1) + '.nii'))

    del covbetaijmap

    # ----------------------------------------------------------------------
    # Calculate COPEs, statistic maps and covariance maps.
    # ----------------------------------------------------------------------
    n_c = len(inputs['contrasts'])

    for i in range(0,n_c):

        # Read in contrast vector
        # Get number of parameters
        cvec = blm_eval(inputs['contrasts'][i]['c' + str(i+1)]['vector'])
        cvec = np.array(cvec)

        # Calculate C\hat{\beta}}
        cbeta = np.matmul(cvec, beta)
        if cvec.ndim == 1:
            cvec = cvec.reshape([1,cvec.shape[0]])

        if inputs['contrasts'][i]['c' + str(i+1)]['statType'] == 'T':

            # A T contrast has only one row so we can output cbeta here
            cbeta = cbeta.reshape(
                        NIFTIsize[0],
                        NIFTIsize[1],
                        NIFTIsize[2],
                        )

            # Output cbeta/cope map
            cbetamap = nib.Nifti1Image(cbeta,
                                       nifti.affine,
                                       header=nifti.header)
            nib.save(cbetamap,
                os.path.join(OutDir, 
                    'blm_vox_beta_c' + str(i+1) + '.nii'))

            # Calculate c'(X'X)^(-1)c
            cvectiXtXcvec = np.matmul(
                np.matmul(cvec, isumXtX),
                np.transpose(cvec)).reshape(n_v)

            # Calculate cov(c\hat{\beta})
            covcbeta = cvectiXtXcvec*resms.reshape(n_v)
            covcbeta = covcbeta.reshape(
                NIFTIsize[0],
                NIFTIsize[1],
                NIFTIsize[2]
                )

            # Output covariance map
            covcbetamap = nib.Nifti1Image(covcbeta,
                                          nifti.affine,
                                          header=nifti.header)
            nib.save(covcbetamap,
                os.path.join(OutDir, 
                    'blm_vox_cov_c' + str(i+1) + '.nii'))


            # To avoid division by zero errors we set the 
            # zero elements to one. This could be updated to 
            # be done with masking.
            covcbeta[covcbeta == 0] = 1  

            # Calculate T statistic image
            tStatc = cbeta/np.sqrt(covcbeta)

            # Output statistic map
            tStatcmap = nib.Nifti1Image(tStatc,
                                        nifti.affine,
                                        header=nifti.header)
            nib.save(tStatcmap,
                os.path.join(OutDir, 
                    'blm_vox_Tstat_c' + str(i+1) + '.nii'))

        if inputs['contrasts'][i]['c' + str(i+1)]['statType'] == 'F':
                
            # Get dimension of cvector
            q = cvec.shape[0]

            # Calculate c'(X'X)^(-1)c
            # (Note C is read in the other way around for F)
            cvectiXtXcvec = np.matmul(
                np.matmul(cvec, isumXtX),
                np.transpose(cvec))

            # Cbeta needs to be nvox by 1 by npar for stacked
            # multiply.
            cbeta = cbeta.reshape(
                cbeta.shape[0],
                cbeta.shape[1],
                1)
            cbeta = cbeta.transpose(1, 0, 2)

            # Calculate masked (c'(X'X)^(-1)c)^(-1) values
            cvectiXtXcvec_m = cvectiXtXcvec[M_inds,:,:]
            icvectiXtXcvec_m = blm_inverse(cvectiXtXcvec_m, ouflow=True).reshape([n_v_m, q*q])

            # Make (c'(X'X)^(-1)c)^(-1) unmasked
            icvectiXtXcvec = np.zeros([n_v, q*q])
            icvectiXtXcvec[M_inds,:]=icvectiXtXcvec_m
            icvectiXtXcvec = icvectiXtXcvec.reshape([n_v, q, q])


            # Calculate the numerator of the F statistic
            cbeta_m = cbeta[M_inds,:,:]
            cbetat_m = cbeta_m.transpose(0,2,1)
            Fnumerator_m = np.matmul(
                cbetat_m,
                np.linalg.solve(cvectiXtXcvec_m, cbeta_m))

            # Calculate the denominator of the F statistic
            Fdenominator_m = q*resms.reshape([n_v])
            Fdenominator_m = Fdenominator_m[M_inds]
            Fdenominator_m = Fdenominator_m.reshape(Fdenominator_m.shape[0])

            # Calculate F statistic.
            print(Fnumerator_m.shape)
            print(Fdenominator_m.shape)
            fStatc_m = Fnumerator_m/Fdenominator_m
            fStatc = np.zeros([n_v])
            fStatc[M_inds]=fStatc
            fStatVolc = fStatc.reshape(
                               NIFTIsize[0],
                               NIFTIsize[1],
                               NIFTIsize[2]
                           )

            # Output statistic map
            fStatcmap = nib.Nifti1Image(fStatVolc,
                                        nifti.affine,
                                        header=nifti.header)
            nib.save(fStatcmap,
                os.path.join(OutDir, 
                    'blm_vox_Fstat_c' + str(i+1) + '.nii'))

            # Make Partial R^2 = qF/(qF+n-p)
            # Mask fStat
            fStatc_m = fStatc[M_inds].reshape(n_v_m, 1)

            # Mask spatially varying n_s
            n_s_sv_m = n_s_sv.reshape(n_v, 1)
            n_s_sv_m = n_s_sv_m[M_inds,:]

            # Calculate partial R2 masked.
            partialR2_m = (q*fStatc_m)/(q*fStatc_m + n_s_sv_m - n_p)

            # Unmask partialR2.
            partialR2 = np.zeros([n_v,1])
            partialR2[M_inds,:] = partialR2_m

            partialR2 = partialR2.reshape(
                               NIFTIsize[0],
                               NIFTIsize[1],
                               NIFTIsize[2]
                           )

            # Output statistic map
            partialR2map = nib.Nifti1Image(partialR2,
                                        nifti.affine,
                                        header=nifti.header)
            nib.save(partialR2map,
                os.path.join(OutDir, 
                    'blm_vox_pr2_c' + str(i+1) + '.nii'))


    # Clean up files
    if len(args)==0:
        os.remove(os.path.join(OutDir, 'nb.txt'))
    shutil.rmtree(os.path.join(OutDir, 'tmp'))

    w.resetwarnings()


# This function inverts matrix A. If ouflow is True,
# special handling is used to account for over/under
# flow. In this case, it assumes that A has non-zero
# diagonals.
def blm_inverse(A, ouflow=False):


    # If ouflow is true, we need to precondition A.
    if ouflow:

        # Work out number of matrices and dimension of
        # matrices. I.e. if we have seven 3 by 3 matrices
        # to invert n_m = 7, d_m = 3.
        n_m = A.shape[0]
        d_m = A.shape[1]

        # Make D to be filled with diagonal elements
        D = np.broadcast_to(np.eye(d_m), (n_m,d_m,d_m)).copy()

        # Obtain 1/sqrt(diagA)
        diagA = 1/np.sqrt(A.diagonal(0,1,2))
        diagA = diagA.reshape(n_m, d_m)

        # Make this back into diagonal matrices
        diaginds = np.diag_indices(d_m)
        D[:, diaginds[0], diaginds[1]] = diagA 

        # Precondition A.
        A = np.matmul(np.matmul(D, A), D)

    # np linalg inverse doesn't handle dim=[1,1]
    if np.ndim(A) == 1:
        iA = 1/A
    else:
        iA = np.linalg.solve(A, np.eye(d_m).reshape(1,d_m,d_m))

    if ouflow:

        # Undo preconditioning.
        iA = np.matmul(np.matmul(D, iA), D)

    return(iA)

# This function calculates the determinant of matrix A/
# stack of matrices A, with special handling accounting
# for over/under flow. 
def blm_det(A):


    # Precondition A.
    # Work out number of matrices and dimension of
    # matrices. I.e. if we have seven 3 by 3 matrices
    # to invert n_m = 7, d_m = 3.
    n_m = A.shape[0]
    d_m = A.shape[1]

    # Make D to be filled with diagonal elements
    D = np.broadcast_to(np.eye(d_m), (n_m,d_m,d_m)).copy()

    # Obtain 1/sqrt(diagA)
    diagA = 1/np.sqrt(A.diagonal(0,1,2))
    diagA = diagA.reshape(n_m, d_m)

    # Make this back into diagonal matrices
    diaginds = np.diag_indices(d_m)
    D[:, diaginds[0], diaginds[1]] = diagA 

    # Calculate DAD.
    DAD = np.matmul(np.matmul(D, A), D)

    # Calculate determinants.
    detDAD = np.linalg.det(DAD)
    detDD = np.prod(diagA, axis=1)
    
    # Calculate determinant of A
    detA = detDAD/detDD

    return(detA)

# This is a small function to help evaluate a string containing
# a contrast vector
def blm_eval(c):

    c = str(c)
    c = c.replace("'", "")
    c = c.replace('][', '], [').replace('],[', '], [').replace('] [', '], [')
    c = c.replace('[ [', '[[').replace('] ]', ']]')
    cs = c.split(' ')
    cf = ''
    for i in range(0,len(cs)):
        cs[i]=cs[i].replace(',', '')
        cf=cf + cs[i]
        if i < (len(cs)-1):
            cf = cf + ', '
        
    return(eval(cf))

if __name__ == "__main__":
    main()
