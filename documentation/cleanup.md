# Spoke/Subscribng VPC Cleanup

1. Change/Delete the "subscribingVpc" tag for/from the VPC
2. Wait for the Deletion of VPNs and VGW associated with subscriber VPC
3. Delete all other "manually" deployed resources in the VPC
4. Delete the Cloudfromation stack related to the subscriber VPC

# Subscribing System Cleanup

1. Delete the subscriber-initalization-setup stack from Cloudformation console
2. You can optionally delete other resources that you created in prerequisite steps
    a. Delete the S3 bucket created for Lambda functions zip file

# Transit System Cleanup

1. Delete the subscriber-initalization-setup stack from Cloudformation console
2. You can optionally delete other resources that you created in prerequisite steps
    a. Delete the S3 bucket created for Lambda functions zip file
    b. Delete the S3 bucket created for PA Bootstrap configuration

