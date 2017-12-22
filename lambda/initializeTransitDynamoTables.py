#from netaddr import IPNetwork
import cfnresponse
import boto3
import ipaddress

def updateAssumeRole(roleName, accountNumbers):
    """Updates Transit Assume Role with Subscriber Account numbers that are passed while creating/updating the initializeTranstiAccount CFT
    """
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

def updateBgpTunnelIpPoolTable(tableName):
    """Updates BgpTunnelIpPool table with  attributes IpSegment, N1T1, N1T2, N2T1, N2T2 and Available=YES
    """
    try:
        dynamodb = boto3.resource('dynamodb')
        table=dynamodb.Table(tableName)
        exceptionList=['169.254.0.0/28', '169.254.1.0/28', '169.254.2.0/28', '169.254.3.0/28', '169.254.4.0/28', '169.254.5.0/28', '169.254.169.240/28']
        tunnelCidrRange = ipaddress.ip_network('169.254.0.0/16')
        count=0
        for subnet_28 in tunnelCidrRange.subnets(new_prefix=28):
            if count<200:
                if not str(subnet_28) in exceptionList:
                    range28 = [subnet_28]
                    for subnet_30 in subnet_28.subnets(new_prefix=30):
                        range28.append(subnet_30)
                    item={
                        'IpSegment': str(range28[0]),
                        'N1T1': str(range28[1]),
                        'N1T2': str(range28[2]),
                        'N2T1': str(range28[3]),
                        'N2T2': str(range28[4]),
                        'Available': 'YES'
                    }   
                    table.put_item(Item=item)
                    count+=1
        print ("Updating {} with 200 entries Done, the last item is: 169.254.12.208/28".format(tableName))
    except Exception as e:
        print ("Updating {} is Failed, Error: {}".format(tableName,str(e)))

def updateTransitConfig(tableName, data):
    """Updates Transit Config table with attributes Property and Value
    """
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
    """Updates Transit PaGroupInfo table with attributes PaGroupName, N1Asn and N2Asn (from 64713-64913), InUse=NO and VpcCount=0
    """
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
    """Updates the Transit VgwAsn table with attributes VgwId from 64512-64612 and InUse=NO
    """
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
    transitConfig = event['ResourceProperties']['TransitConfig']
    bucketName = event['ResourceProperties']['TransitVpnBucketName']
    bgpPool = event['ResourceProperties']['TransitBgpTunnelIpPool']
    vgwAsn = event['ResourceProperties']['TransitVgwAsn']
    paGropuInfo = event['ResourceProperties']['TransitPaGroupInfo']
    ipNetwork1 = event['ResourceProperties']['TransitVpcDmzAz1SubnetGateway']
    ipNetwork2 = event['ResourceProperties']['TransitVpcDmzAz2SubnetGateway']
    checkStackStatusLambda = event['ResourceProperties']['CheckStackStatusLambda']
    configureTransitVpnLambda = event['ResourceProperties']['ConfigureTransitVpnLambda']
    rebalancePaGroupsLambda = event['ResourceProperties']['RebalancePaGroupsLambda']
    deleteTransitVpnConfigurationLambda = event['ResourceProperties']['DeleteTransitVpnConfigurationLambda']
    mgmtAz1 = event['ResourceProperties']['MgmtAz1SubnetId']
    mgmtAz2 = event['ResourceProperties']['MgmtAz2SubnetId']


    ip1 = ipaddress.ip_network(ipNetwork1)
    ip2 = ipaddress.ip_network(ipNetwork2)
    ip1List = list(ip1)
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
        updateBgpTunnelIpPoolTable(bgpPool)
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
    elif event['RequestType'] == 'Delete':
        s3 = boto3.resource('s3')
        bucket = s3.Bucket(bucketName)
        bucket.objects.all().delete()
        bucket.delete()
        print("Successully Deleted S3 Objects and the Bucket: {}".format(bucketName))
        try:
            import time
            lambda_conn = boto3.client('lambda')
            lambda_conn.delete_function(FunctionName=checkStackStatusLambda)
            lambda_conn.delete_function(FunctionName=configureTransitVpnLambda)
            lambda_conn.delete_function(FunctionName=rebalancePaGroupsLambda)
            lambda_conn.delete_function(FunctionName=deleteTransitVpnConfigurationLambda)
            print("Deleted Lambda launched in VPCs")
            ec2_conn = boto3.client('ec2')
            filters = [{'Name':'subnet-id','Values':[mgmtAz1,mgmtAz2]}]
            interfaces = ec2_conn.describe_network_interfaces(Filters=filters)['NetworkInterfaces']
            if interfaces:
                for interface in interfaces:
                    print("Detaching Network Interface: {}".format(interface['NetworkInterfaceId']))
                    ec2_conn.detach_network_interface(AttachmentId=interface['Attachment']['AttachmentId'])
                    print("Detached Network Interface: {}".format(interface['NetworkInterfaceId']))
            print("Sleeping for 5 seconds")
            time.sleep(5)
            if interfaces:
                for interface in interfaces:
                    print("Deleting Network Interface: {}".format(interface['NetworkInterfaceId']))
                    ec2_conn.delete_network_interface(NetworkInterfaceId=interface['NetworkInterfaceId'])
                    print("Deleted Network Interface: {}".format(interface['NetworkInterfaceId']))
            print("Deleting Mmgt subnets: {},{}".format(mgmtAz1,mgmtAz2))
            #ec2_conn.delete_security_group(GroupId=trustedSg)
            ec2_conn.delete_subnet(SubnetId=mgmtAz1)
            ec2_conn.delete_subnet(SubnetId=mgmtAz2)
            #ec2_conn.delete_vpc(VpcId=vpcId)
            print("Deleted Mmgt subnets: {},{}".format(mgmtAz1,mgmtAz2))
            cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData, "CustomResourcePhysicalID")
        except Exception as e:
            print("Erro While deleting the Network Interfaces|TrustedSg|MgmtSubnets|Vpc. Error: {}".format(str(e)))
            cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData, "CustomResourcePhysicalID")   
        cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData, "CustomResourcePhysicalID")
