# Prerequisites to Setup Transit solution
This document talks about prerequisites required for setting up the Transit solution. This mainly covers creating the S3 buckets for setting up the Transit and Subscriber environments.

It involves,
1. S3 bucket for bootstrap
2. S3 bucket for Lambda

Clone the "palo-alto-scripts" repository for required files to setup the Transit environment.

## Transit Environment
Follow the below steps to setup the S3 buckets in Transit account.

### S3 bucket for bootstrap
S3 bucket is required to perform the Palo Alto bootstrapping function.
Find the "pa_bootstrap.zip" file in "prerequisites" directory of the cloned repository, unzip it and upload them to the bootstrapping S3 bucket.

1. This bucket contains the following folders, which accounts for successful bootstrapping.
![alt text](images/s3_bucket_folders.png "S3 bucket folders")

2. The config folder contains the “bootstrap.xml” file and the “init-cfg.txt” file:
![alt text](images/config_folder.png "config folder")

3. The “license” folder contains a file named “authcodes” with the authcode license for the Palo Alto VM. Provide valid authcode in the file.

4. The “content” and “software” folders have empty dummy files created in them.

### S3 bucket for Lambda
An S3 bucket is required to store the "lambda.zip" file that helps create all the necessary Lambda functions. It will also have the CFT to create PAGroup Servers (paGroupCft.json)

Find "paGroupCFT.json" files under "cfts" directory. Add the contents of "lambda" directory to "lambda.zip" (do not include the lambda directory) then upload the files to S3 bucket. "lambda.zip" file is available in "prerequisites" directory.

## Subscriber Environment
Follow the below steps to setup the S3 buckets in Subscriber account.

### S3 bucket for Lambda
An S3 bucket is required to store the "lambda.zip" file that helps create all the necessary Lambda functions. It will also have the CFT to create Subscriber VPC.

Find the "subscriberVpcCFT.json" file under "cfts" directory, add the contents of "lambda" directory to lambda.zip and upload these files into the S3 bucket. "Lambda.zip" file is available in "prerequisites" directory.

