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

def main():

    # Change to blm directory
    os.chdir(os.path.dirname(os.path.realpath(__file__)))

    # Obtain necessry inputs
    with open(os.path.join('..','blm_defaults.yml'), 'r') as stream:
        inputs = yaml.load(stream)
    SVFlag = inputs['SVFlag']
    OutDir = inputs['outdir']
    
    # Read the matrices from the first batch.
    sumXtX = np.loadtxt(os.path.join(OutDir,"tmp","XtX1.csv"), 
                        delimiter=",")
    sumXtY = np.loadtxt(os.path.join(OutDir,"tmp","XtY1.csv"), 
                        delimiter=",")
    sumYtY = np.loadtxt(os.path.join(OutDir,"tmp","YtY1.csv"), 
                        delimiter=",")
    nmapb  = nib.load(os.path.join(OutDir,"tmp", "blm_vox_n_batch1.nii"))
    nmapd = nmapb.get_data()

    # Delete the files as they are no longer needed.
    os.remove(os.path.join(OutDir,"tmp","XtX1.csv"))
    os.remove(os.path.join(OutDir,"tmp","XtY1.csv"))
    os.remove(os.path.join(OutDir,"tmp","YtY1.csv"))

    # Work out how many files we need.
    XtX_files = glob.glob(os.path.join(OutDir,"tmp","XtX*"))

    # Cycle through batches and add together results.
    for batchNo in range(2,(len(XtX_files)+2)):
        
        # Sum the batches.
        sumXtX = sumXtX + np.loadtxt(
            os.path.join(OutDir,"tmp","XtX" + str(batchNo) + ".csv"), 
                         delimiter=",")

        sumXtY = sumXtY + np.loadtxt(
            os.path.join(OutDir,"tmp","XtY" + str(batchNo) + ".csv"), 
                         delimiter=",")

        sumYtY = sumYtY + np.loadtxt(
            os.path.join(OutDir,"tmp","YtY" + str(batchNo) + ".csv"), 
                         delimiter=",")

        # Obtain the full nmap.
        nmapd = nmapd + nib.load(os.path.join(OutDir,"tmp", 
            "blm_vox_n_batch" + str(batchNo) + ".nii")).get_data()
        
        # Delete the files as they are no longer needed.
        os.remove(os.path.join(OutDir, "tmp","XtX" + str(batchNo) + ".csv"))
        os.remove(os.path.join(OutDir, "tmp","XtY" + str(batchNo) + ".csv"))
        os.remove(os.path.join(OutDir, "tmp","YtY" + str(batchNo) + ".csv"))
        os.remove(os.path.join(OutDir, "tmp", "blm_vox_n_batch" + str(batchNo) + ".nii"))

    
    # Output final n map
    nmap = nib.Nifti1Image(nmapd,
                           nmapb.affine,
                           header=nmapb.header)
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

    # Mask and reshape if we are using a spatially varying design.
    if SVFlag:

        # Remove zero lines and convert back to number voxels (in
        # mask) by number of parametes by number of parameters)
        sumXtX = sumXtX.reshape([sumXtX.shape[0], 
                     int(np.sqrt(sumXtX.shape[1])),
                     int(np.sqrt(sumXtX.shape[1]))])
        sumXtX_m = sumXtX[np.where(np.linalg.det(sumXtX)!=0)[0]]
        
        isumXtX_m = np.linalg.inv(sumXtX_m).reshape(
                      [sumXtX_m.shape[0],
                       int(sumXtX_m.shape[1])*int(sumXtX_m.shape[2])])

        isumXtX = np.zeros([sumXtX.shape[0],
                            int(sumXtX.shape[1])*int(sumXtX.shape[2])])

        isumXtX[np.where(np.linalg.det(sumXtX)!=0)[0]]=isumXtX_m

        isumXtX = isumXtX.reshape([isumXtX.shape[0],
                                   int(np.sqrt(isumXtX.shape[1])),
                                   int(np.sqrt(isumXtX.shape[1]))])


    # If we are not using a spatially varying design, inverse in
    # the normal manner.
    else:
        # np linalg inverse doesn't handle dim=[1,1]
        if np.ndim(sumXtX) == 1:
            isumXtX = 1/sumXtX
        else:
            isumXtX = np.linalg.inv(sumXtX)

    # Read in the nifti size.
    with open(inputs['Y_files']) as a:
        nifti = nib.load(a.readline().replace('\n', ''))

    NIFTIsize = nifti.shape

    # If we are doing spatially varying we need to reshape XtY.
    if SVFlag:
        sumXtY = sumXtY.transpose()
        sumXtY = sumXtY.reshape([sumXtY.shape[0], sumXtY.shape[1], 1])
    
    beta = np.matmul(isumXtX, sumXtY)
    
    if SVFlag:
        beta = beta.reshape([beta.shape[0], beta.shape[1]]).transpose()

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

    # Reshape beta along smallest axis for quicker
    # residual calculation
    beta_rs = np.zeros([beta.shape[1], beta.shape[0], 1])
    beta_rs_t = np.zeros([beta.shape[1], 1, beta.shape[0]])
    for i in range(0,beta.shape[0]):
        
       beta_rs[:, i, 0] = beta[i,:]
       beta_rs_t[:, 0, i] = beta[i,:]

    # Calculate Beta transpose times XtX and delete the
    # now redudundant matrices.
    betatXtX = np.matmul(beta_rs_t, sumXtX)
    del beta_rs_t, sumXtX

    # Multiply BetatXtX by Beta and delete the reduundant
    # matrices.
    betatXtXbeta = np.matmul(betatXtX, beta_rs)
    del betatXtX, beta_rs

    # Reshape betat XtX beta
    betatXtXbeta = np.reshape(betatXtXbeta, betatXtXbeta.shape[0])

    # Residual sum of squares
    ete = sumYtY - betatXtXbeta
    ete = ete.reshape(int(NIFTIsize[0]),
                      int(NIFTIsize[1]),
                      int(NIFTIsize[2]))

    # Get residual mean squares by dividing by degrees of
    # freedom
    if not SVFlag:

        # Get number of scans and number of parameters
        X = np.loadtxt(inputs['X'], delimiter=',')
        n_s = X.shape[0]
        n_p = X.shape[1]

        # In non spatially varying the degrees of freedom
        # are fixed across voxels
        resms = ete/(n_s-n_p)

    else:
        
        # Get number of scans and number of parameters
        X = np.loadtxt(inputs['X'], delimiter=',')
        n_s = X.shape[0]
        n_p = X.shape[1]

        # Load in the spatially varying number of scans.
        n_s = nib.load(os.path.join(OutDir,'blm_vox_n.nii'))
        n_s = n_s.get_data()

        # To avoid division by zero errors we set the 
        # zero elements to one.
        n_s[n_s == 0] = 1

        # In spatially varying the degrees of freedom
        # varies across voxels
        resms = ete/(n_s-n_p)

    # Output ResSS.
    msmap = nib.Nifti1Image(resms,
                            nifti.affine,
                            header=nifti.header)
    nib.save(msmap, os.path.join(OutDir,'blm_vox_resms.nii'))

    # calculate beta covariance maps
    if not SVFlag:

        # Output variance for each pair of betas
        for i in range(0,isumXtX.shape[0]):
            for j in range(0,isumXtX.shape[1]):

                    # Calculate covariance of beta i and beta j.
                    covbetaij = resms*isumXtX[i,j]

                    # Output covariance map
                    covbetaijmap = nib.Nifti1Image(covbetaij,
                                                   nifti.affine,
                                                   header=nifti.header)
                    nib.save(covbetaijmap,
                        os.path.join(OutDir, 
                            'blm_vox_cov_b' + str(i+1) + ',' + str(j+1) + '.nii'))

        del covbetaijmap

    else:

        # Output variance for each pair of betas
        for i in range(0,isumXtX.shape[1]):
            for j in range(0,isumXtX.shape[2]):

                    covbetaij = np.multiply(resms,
                        isumXtX[:,i,j].reshape(
                            resms.shape[0],
                            resms.shape[1],
                            resms.shape[2],
                            ))
                        
                    # Output covariance map
                    covbetaijmap = nib.Nifti1Image(covbetaij,
                                                   nifti.affine,
                                                   header=nifti.header)
                    nib.save(covbetaijmap,
                        os.path.join(OutDir, 
                            'blm_vox_cov_b' + str(i+1) + ',' + str(j+1) + '.nii'))

        del covbetaijmap

    # Loop through contrasts, outputting COPEs, statistic maps
    # and covariance maps.
    n_c = len(inputs['contrasts'])

    for i in range(0,n_c):

        # Read in contrast vector
        cvec = np.array(inputs['contrasts'][i]['c' + str(i+1)]['vector'])

        # Calculate C\hat{\beta}}
        cbeta = np.matmul(cvec, beta)

        print(inputs['contrasts'][i]['c' + str(i+1)]['statType'])


        if inputs['contrasts'][i]['c' + str(i+1)]['statType'] == 'T':

            # A T contrast has only one row so we can output cbeta here
            cbeta = cbeta.reshape(
                        resms.shape[0],
                        resms.shape[1],
                        resms.shape[2],
                        )

            # Output cbeta/cope map
            cbetamap = nib.Nifti1Image(cbeta,
                                       nifti.affine,
                                       header=nifti.header)
            nib.save(cbetamap,
                os.path.join(OutDir, 
                    'blm_vox_beta_c' + str(i+1) + '.nii'))

            if not SVFlag:

                # Calculate c'(X'X)^(-1)c
                cvectiXtXcvec = np.matmul(
                    np.matmul(np.transpose(cvec), isumXtX),
                    cvec)

                # Calculate cov(c\hat{\beta})
                covcbeta = cvectiXtXcvec*resms

                # Output covariance map
                covcbetamap = nib.Nifti1Image(covcbeta,
                                              nifti.affine,
                                              header=nifti.header)
                nib.save(covcbetamap,
                    os.path.join(OutDir, 
                        'blm_vox_cov_c' + str(i+1) + '.nii'))

            else:

                # Calculate c'(X'X)^(-1)c
                cvectiXtXcvec = np.matmul(
                    np.matmul(np.transpose(cvec), isumXtX),
                    cvec)

                print(cvectiXtXcvec.shape)

                # Calculate cov(c\hat{\beta})
                covcbeta = cvectiXtXcvec*resms.reshape(
                    resms.shape[0]*resms.shape[1]*resms.shape[2]
                    )

                print(covcbeta.shape)

                covcbeta = covcbeta.reshape(
                    resms.shape[0],
                    resms.shape[1],
                    resms.shape[2]
                    )

                # Output covariance map
                covcbetamap = nib.Nifti1Image(covcbeta,
                                              nifti.affine,
                                              header=nifti.header)
                nib.save(covcbetamap,
                    os.path.join(OutDir, 
                        'blm_vox_cov_c' + str(i+1) + '.nii'))

            print(cvectiXtXcvec.shape)
            print(cbeta.shape)
            print(resms.shape)
            print(inputs['contrasts'][i]['c' + str(i+1)]['statType'])


            # To avoid division by zero errors we set the 
            # zero elements to one.
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
        
            # Not spatially varying
            if not SVFlag:
                
                # Get dumension of cvector
                q = cvec.shape[1]

                # Calculate c'(X'X)^(-1)c
                cvectiXtXcvec = np.matmul(
                    np.matmul(np.transpose(cvec), isumXtX),
                    cvec)#XXX duplication - should remove in cleanup

                print('F')
                print(q)
                print(cvectiXtXcvec.shape)
                print(cbeta.shape)



    # Clean up files
    os.remove(os.path.join(OutDir, 'nb.txt'))
    shutil.rmtree(os.path.join(OutDir, 'tmp'))

    w.resetwarnings()


if __name__ == "__main__":
    main()
