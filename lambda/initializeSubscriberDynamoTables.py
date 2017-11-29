from netaddr import IPNetwork
import cfnresponse
import boto3

def updateSubscriberConfig(tableName, data):
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

    if event['RequestType'] == 'Create':
        #Update Subscriber Config Table
        updateSubscriberConfig(event['ResourceProperties']['SubscriberConfig'], event['ResourceProperties'])
    cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData, "CustomResourcePhysicalID")
