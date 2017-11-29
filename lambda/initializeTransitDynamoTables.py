from netaddr import IPNetwork
import cfnresponse
import boto3

def updateAssumeRole(roleName, accountNumbers):
    iam_conn = boto3.client('iam')
    response = iam_conn.get_role(RoleName=roleName)

    if len(accountNumbers.split(','))>1:
        awsList = []
        for account in accountNumbers.split(','):
            awsList.append('arn:aws:iam::'+account+':root')
        response['Role']['AssumeRolePolicyDocument']['Statement'][0]['Principal']['AWS']=awsList
        doc = str(response['Role']['AssumeRolePolicyDocument'])
        policyDoc = doc.replace('\'','\"')
        iam_conn.update_assume_role_policy(RoleName=roleName,PolicyDocument=policyDoc)
        print("{} is updated with new Account numbers, Response: {}".format(roleName, policyDoc))
    else:
        response['Role']['AssumeRolePolicyDocument']['Statement'][0]['Principal']['AWS'] = 'arn:aws:iam::'+accountNumbers+':root'
        doc = str(response['Role']['AssumeRolePolicyDocument'])
        policyDoc = doc.replace('\'','\"')
        iam_conn.update_assume_role_policy(RoleName=roleName,PolicyDocument=policyDoc)
        print("{} is updated with new Account numbers, Response: {}".format(roleName, policyDoc))

def updateBgpTunnelIpPoolTable(tableName,bucketName):
    try:
        s3_client = boto3.client('s3')
        s3_client.download_file(bucketName, 'availableVPNCidr.txt', '/tmp/cidr.txt')
        dynamodb = boto3.resource('dynamodb')
        table=dynamodb.Table(tableName)
        with open('/tmp/cidr.txt', 'r') as infile:
            for line in infile:
                data=line.split('|')
                item={
                    'IpSegment': data[0],
                    'N1T1': data[1],
                    'N1T2': data[2],
                    'N2T1': data[3],
                    'N2T2': data[4],
                    'Available': 'YES'
                }
                table.put_item(Item=item)
        print ("Updating {} is Done".format(tableName))
    except Exception as e:
        print ("Updating {} is Failed, Error: {}".format(tableName,str(e)))

def updateTransitConfig(tableName, data):
    try:
        dynamodb = boto3.resource('dynamodb')
        table=dynamodb.Table(tableName)
        #Removing SubscriberAccounts key from data to avoid AttributeValue may not contain an empty string error
        data = {k: v for k, v in data.items() if v}
        for key,value in data.items():
            item={'Property':key,'Value':value}
            table.put_item(Item=item)
        print ("Successfully updated Transit Config Table")
    except Exception as e:
        print ("Updating {} is Failed, Error: {}".format(tableName,str(e)))

def updatePaGroupInfo(tableName):
    try:
        dynamodb = boto3.resource('dynamodb')
        table=dynamodb.Table(tableName)
        #Update PaGroupInfo table with PaGroup{id}, N1Asn and N2Asn with range 64713-65113
        asnStart=64713
        for i in range(1,100+1):
            j=asnStart
            for j in range(j, j+3):
                item={
                    'PaGroupName': 'PaGroup'+str(i),
                    'N1Asn': str(j),
                    'N2Asn': str(j+1),
                    'InUse': 'NO',
                    'VpcCount': 0
                }
                asnStart=j+2
                table.put_item(Item=item)
                break
        print("Updating {} is Done".format(tableName))
    except Exception as e:
        print ("Updating {} is Failed, Error: {}".format(tableName,str(e)))

def updateVgwAsn(tableName):
    try:
        dynamodb = boto3.resource('dynamodb')
        table=dynamodb.Table(tableName)
        #Update VgwAsn Table with Privat ASN numbers between 64512-64612 -> for 100 VPC 100 VGW
        for i in range(64512,64612+1):
            table.put_item(Item={'VgwAsn':str(i),'InUse':'NO'})
        print ("Updating {} is Done".format(tableName))
    except Exception as e:
        print ("Updating {} is Failed, Error: {}".format(tableName,str(e)))

def lambda_handler(event, context):
    print(event)
    responseData = {}
    responseData['data'] = 'Success'

    roleName =  event['ResourceProperties']['TransitAssumeRoleName']
    accountNumbers =  event['ResourceProperties']['SubscriberAccounts']
    bucketName = event['ResourceProperties']['LambdaCodeBucketName']
    transitConfig = event['ResourceProperties']['TransitConfig']
    bgpPool = event['ResourceProperties']['TransitBgpTunnelIpPool']
    vgwAsn = event['ResourceProperties']['TransitVgwAsn']
    paGropuInfo = event['ResourceProperties']['TransitPaGroupInfo']
    ipNetwork1 = event['ResourceProperties']['TransitVpcDmzAz1SubnetGateway']
    ipNetwork2 = event['ResourceProperties']['TransitVpcDmzAz2SubnetGateway']

    ip1 = IPNetwork(ipNetwork1)
    ip1List = list(ip1)
    ip2 = IPNetwork(ipNetwork2)
    ip2List = list(ip2)
    
    event['ResourceProperties']['TransitVpcDmzAz1SubnetGateway'] = str(ip1List[1])
    event['ResourceProperties']['TransitVpcDmzAz2SubnetGateway'] = str(ip2List[1])
    
    responseData['TransitVpcDmzAz2SubnetGateway'] = str(ip2List[1])
    responseData['TransitVpcDmzAz1SubnetGateway'] = str(ip1List[1])

    if event['RequestType'] == 'Create':
        #Update Assume Role
        if accountNumbers:
            updateAssumeRole(roleName, accountNumbers)
        #Update DynamoDB TranstiConfig Table
        updateTransitConfig(transitConfig, event['ResourceProperties'])
        #Update DynamoDB BgPTunnleIpPool Table
        updateBgpTunnelIpPoolTable(bgpPool,bucketName)
        #Update DynamoDB VgwAsn Table
        updateVgwAsn(vgwAsn)
        #Update DynamoDB PaGroupInfo Table
        updatePaGroupInfo(paGropuInfo)
        #Return gateway ips for subnets                    
        cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData, "CustomResourcePhysicalID")

    elif event['RequestType'] == 'Update':
        if accountNumbers:
            updateAssumeRole(roleName, accountNumbers)
            cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData, "CustomResourcePhysicalID")
        else:
            cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData, "CustomResourcePhysicalID")
    else:
        cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData, "CustomResourcePhysicalID")
