import cfnresponse
import boto3

def updateSubscriberConfig(tableName, data):
    """Updates the SubscriberConfig table with attributes Property and Value
    """
    try:
        dynamodb = boto3.resource('dynamodb')
        table=dynamodb.Table(tableName)
        data = {k: v for k, v in data.items() if v}
        for key,value in data.items():
            item={'Property':key,'Value':value}
            table.put_item(Item=item)
        print ("Successfully updated Subscriber Config Table")
    except Exception as e:
        print ("Updating {} is Failed, Error: {}".format(tableName,str(e)))

def lambda_handler(event, context):
    print(event)
    responseData = {}
    responseData['data'] = 'Success'
    bucketName = event['ResourceProperties']['CloudTrailBucketName'] 

    if event['RequestType'] == 'Create':
        #Update Subscriber Config Table
        updateSubscriberConfig(event['ResourceProperties']['SubscriberConfig'], event['ResourceProperties'])
        cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData, "CustomResourcePhysicalID")
    elif event['RequestType'] == 'Delete':
        s3 = boto3.resource('s3')
        bucket = s3.Bucket(bucketName)
        bucket.objects.all().delete()
        bucket.delete()
        print("Successully Deleted S3 Objects and the Bucket: {}".format(bucketName))
        cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData, "CustomResourcePhysicalID")
    cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData, "CustomResourcePhysicalID")


