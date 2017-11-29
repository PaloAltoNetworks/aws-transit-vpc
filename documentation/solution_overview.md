# Solution documentation

## Brief description about the solution
This solution automates baseline Firewall Services VPC solution. In baseline Firewall services VPC there are two VPCs.
 1. A HUB VPC where Palo Alto Firewall devises will be deployed
 2. One or more Spoke VPCs located in one or more AWS accounts,  where workloads are deployed

All Spoke VPCs are connected to Palo Alto Firewall located in HUB VPC. All Spoke VPCs can talk to each other by transiting over Palo Alto (PA) servers located in HUB VPC. For redundancy, there will be a pair of PA server attached to a VPC and each of the node in the pair will be located in a different availability zone.

## Design considerations
1. When a Spoke VPC or Subscribing VPC is created, it should trigger automatic configuration of VPN with a PA server pair in HUB VPC

2. For redundancy there should be two PA Servers establishing VPN with each VPC and each PA server should be in separate availability zone

3. Each PA Group (acts as a single logical unit and has two nodes in two az for redundancy) has a limit on maximum number of VPCs (X) it can establish VPN with. When number of VPC exceeds the maximum limit that can be supported by existing number of PA Groups, a new PA Group should be created

4. When a new Subscriber VPC is created, it should automatically get associated with a PA group which has capacity

5. When new PA Groups are created to support new VPCs, each node of the newly created PA Group should establish BGP peer with nodes associated with other PA groups which belong to the same AZ

6. To avoid traffic from Subscribing VPC to pass through both the VPN tunnels (tunnel to Node1 and Node2 of the PA group it is associated with), BGP configuration on one of the node should have an MED value set that is different from the other. To satisfy this requirement, node1 of all PA group will be using "active" bgp peer group and node2 will be using "passive" bgp peer group. The difference between these peer groups is that "passive" peer group has an MED value set and "active" doesn't

7. Minimum manual steps from a customer who want to setup this system

8. Un subscription from the system should be automatic

9. System shouldn't spin up new PA (or PA Group) if existing system have capacity to host new VPC

10. When configuring AWS VPN, AWS allocates /30 ip ranges for each tunnel associated with a VPN GW. There could be conflict if subscribers are from different region or from different AWS accounts.

11. To avoid conflict, each PA node should have unique ASN

12. To avoid conflict, each VGW associated with subscribing VPC should have unique ASN

## Design Overview
This system can be split into two logical pieces
1. Task  
2. Transit system
3. Subscriber system

### Task and Action
Task is a JSON object exchanged between Transit system and subscriber system or between states within a system. The Task has information about next operation (Action) to be performed and data needed to perform next operation. One or lambda function associated with State machine will execute the "Action" defined by the "Task"

eg:
{
    'Action': 'ConfigureSubscribingVpcVpn',  # Next action to perform
    'IpSegment': "169.254.8.0/28",           # Supernet of all /30s for a PA Group
    'N1T1': "169.254.8.0/30",                # /30 ip range for Node1 IPSec Tunnel 1
    'N1T2': "169.254.8.4/30",                # /30 ip range for Node1 IPSec Tunnel 2
    'N1Eip': "<Node1 EIP>",
    'N1Asn': "<Node1 BGP ASN>",
    'N2T1': "169.254.8.8/30",                # /30 ip range for Node2 IPSec Tunnel 1
    'N2T2': "169.254.8.12/30",               # /30 ip range for Node2 IPSec Tunnel 2
    'N2Eip': "<Node2 EIP>"'
    'N2Asn': "<Node2 BGP ASN>",
    'PaGroupName': "<PA Group Name>",
    'Rebalance' : "False",
    'VpcId': "<Subscriber VPC ID>",
    'VpcCidr': "<Subscriber VPC CIDR>",
    'Region': "<Subscriber VPC AWS Region>",
    'TransitVpnBucketName': "<Bucket to push VPN configuration file>",
    'TransitAssumeRoleArn': "<IAM Role to assume while contacting Transit system>",
    'TransitSnsArn': "<Transit SNS ARN>"
}

### Transit system
This logical system takes care of automatically configuring VPN and managing resources on the "Transit"/"HUB" side. Following are few tasks done by transit system
- PA Group deployment
- Configuring bgp peering between PA Groups
- Providing unique ASN to Subscriber for creating VGW
- Providing PA Group information (Node1 and Node2 ip) for CGW creation
- Providing unique IP Pool for AWS IPSec vpn configuration
- Configure IPSec VPN with Subscriber VPC
- Deleting VPN with Subscriber VPC

[Diagrmam links here]

#### Components of transit system
1. Transit SNS
2. Transit Task Handler (Transit decider) (lambda)
3. BgpTunnelPool (DynamoDB Table)
4. PgGroupInfo (DynamoDB Table)
5. TransitConfig (DynamoDB Table)
6. VgwAsn (DynamoDB Table)
7. VpcTable (DynamoDB Table)
8. HighPriorityQueue(or DeleteQueue)
9. LowPriorityQueue(or CreateQueue)
10. Transit State machine (AWS Stepfunction)

##### Transit SNS

##### Transit Task Handler

##### BgpTunnelPool (DynamoDB Table)
| IpSegment       | Available | N1T1            |  N1T2           | N2T1            | N2T2            |
| --------------- | --------- | --------------- | --------------- | --------------- | --------------- |
| 169.254.6.0/28  | Yes       | 169.254.6.0/30  | 169.254.6.4/30  | 169.254.6.8/30  | 169.254.6.12/30 |
| 169.254.6.16/28 | Yes       | 169.254.6.20/30 | 169.254.6.24/30 | 169.254.6.28/30 | 169.254.6.32/30 |


##### PgGroupInfo (DynamoDB Table)
| PaGroupName | InUse | N1Asn  |  N2Asn | VpcCount |
| ----------- | ----- | ------ | ------ | -------- |
| PaGroup1    | Yes   | 64827  | 64828  | 0        |

##### TransitConfig (DynamoDB Table)
| Property                         | Value
| -------------------------------- | -------------------------------------------------------------------------------- |
| TransitVpcTrustedSecurityGroupId | sg-xxxxxxx                                                                       |
| UserName                         | admin                                                                            |
| PaGroupMaxVpc                    | 4                                                                                |
| TransitAssumeRoleName            | TransitAssumeRole-xxxx                                                           |
| TransitVpcTrustedSecurityGroupId | sg-xxxxxxx                                                                       |
| PaGroupInstanceProfileName       | init-transit-ac-paGroupInstanceProfile-hsfajfdak                                 |
| DeLicenseApiKey                  | HelloWorld                                                                       |
| Password                         | password                                                                         |
| TransitConfig                    | TransitConfig-hjgf                                                               |
| TransitVgwAsn                    | VgwAsn-init-transit-ac                                                           |
| TransitVpcDmzAz1SubnetGateway    | 10.100.0.1                                                                       |
| TransitVpnBucketName             | pa-transit-vpn-configuration-bucket                                              |
| TransitVpcTable                  | VpcTable                                                                         |
| SshKeyName                       | palo-alto-ssh-key                                                                |
| TransitSnsArn                    | arn:aws:sns:us-east-1:123456789:17KC0HO1YE7SN                                    |
| TransitPaGroupInfo               | PaGroupInfo-init-transit-ac                                                      |
| PaBootstrapBucketName            | pa-bootstrap-bucket                                                              |
| TransitVpcDmzAz2SubnetGateway    | 10.100.0.122                                                                     |
| PaBootstrapBucketAccessRole      | paBootstrapBucketAccessRole-17KC0HO1YE7SN                                        |
| PaGroupTemplateUrl               | https://s3.amazonaws.com/pacft/transit_pa_group.json                             |
| TransitBgpTunnelIpPool           | BgpTunnelIpPool                                                                  |
| SubscriberAccounts               | 987654321                                                                        |
| TransitVpcDmzAz1SubnetId         | subnet-xxxxxxx                                                                   |
| TransitVpcDmzAz2SubnetId         | subnet-xxxxxxy                                                                   |
| TransitVpcMgmtAz1SubnetId        | subnet-xxxxxxz                                                                   |
| LambdaCodeBucketName             | kumar-cloudtrail-bucket                                                          |
| Region                           | us-east-1                                                                        |
| TransitStateMachineArn           | arn:aws:states:us-east-1:123456789:stateMachine:TransitStateMachine-uAni8eqObjI2 |
| ServiceToken                     | arn:aws:lambda:us-east-1:123456789:function:TransitInitializeLambda-5UNZJCAZX05  |
| TransitVpcMgmtAz2SubnetId        | subnet-xxxxxyz                                                                   |
| TransitPriorityQueue             | https://sqs.us-east-1.amazonaws.com/123456789/PriorityQueue.fifo                 |
| TransitAssumeRoleArn             | arn:aws:iam::123456789:role/TransitAssumeRole                                    |
| TransitNormalQueue               | https://sqs.us-east-1.amazonaws.com/123456789/NormalQueue.fifo                   |


##### VgwAsn (DynamoDB Table)
| VgwAsn | InUse | VpcId       | VpcCidr    |
| ------ | ----- | ----------- | ---------- |
| 64076  | Yes   | vpc-xxxxxxx | 10.x.x.x/x |

##### VpcTable (DynamoDB Table)
| VpcId       |	VpcCidr    | PaGroupName |	Node1VpnId | Node2VpnId  | SubscriberAssumeRoleArn  | SubscriberSnsArn         | CurrentStatus |	IpSegment |
| ----------- | ---------- | ----------- | ----------- | ----------- | ------------------------ | ------------------------ | ------------- | ------------ |
| vpc-xxxxxxx | 10.x.x.x/x | paGroup1    | vpn-xxxxxxx | vpn-xxxxxxy | arn:iam:987654321:iamarn | arn:sns:987654321:snsarn | InProgress    | 10.x.x.x/x   |


##### HighPriorityQueue(or DeleteQueue)

##### LowPriorityQueue(or CreateQueue)

##### Transit State machine (AWS Stepfunction)






### Subscriber system
This logical system takes care of automatically configuring VPN at the "subscriber" side. Following are few tasks done by Subscriber system
- Detect VPC creation
- Gather information needed to configure VPN with PA group
- Create VGW, CGW, IPSec configuration
- Notify transit system with VPN configuration information so that Transit system can complete VPN configuration
- Detect VPN delete operation and trigger VPN delete operation from Transit system

[Diagram here]

#### Components of Subscriber system
1. Subscriber SNS
2. CloudTrail and CloudTrailLambda
3. SubscriberDecider Lambda
4. SubscriberVpcVpnTable
5. SubscriberLocalDb
6. SubscriberConfig
7. SubscriberQueue
8. Subscriber State machine

##### Subscriber SNS

##### CloudTrail and CloudTrailLambda

##### SubscriberDecider Lambda

##### SubscriberVpcVpnTable (DynamoDB Table)
| VpnId       | VpcId       | PaGroup    | PaNode  |
| ----------- | ----------- | ---------- | ------- |
| vpn-xxxxxxx | vpc-xxxxxxx | PaGroup1   | N1      |
| vpn-xxxxxxy | vpc-xxxxxxx | PaGroup1   | N2      |

##### SubscriberLocalDb (DynamoDB Table)
| VpcId       | VpcCidr     | VgwId       | VgwAsn | PaGroup  | CgwN1       | CgwN2       | VpnN1       | VpnN2       |
| ----------- | ----------- | ----------- | ------ | -------- | ----------- | ----------- | ----------- | ----------- |
| vpc-xxxxxxx | 10.x.x.x./x | vgw-xxxxxxx | 64827  | PaGroup1 | cgw-xxxxxxx | cgw-xxxxxxy | vpn-xxxxxxx | vpn-xxxxxxy |

##### SubscriberConfig (DynamoDB Table)
| Property                  | Value                                                                         |
| ------------------------- | ----------------------------------------------------------------------------- |
| TransitSNSTopicArn        | arn:aws:sns:us-east-1:12345667489:transitSns-arn                              |
| SubscriberAssumeRoleArn   | arn:aws:iam::987654321:role/SubscriberAssumeRole-arn                          |
| SubscriberQueueUrl        | https://sqs.us-east-1.amazonaws.com/987654321/subscriberFifoQueue.fifo        |
| SubscriberStateMachineArn | arn:aws:states:us-east-1:987654321:stateMachine:SubscrierStateMachine-Lafhjdu |
| SubscriberSnsArn          | arn:aws:sns:us-east-1:987654321:subscriberSnsTopic                            |
| SubscriberLocalDb         | SubscriberLocalDb                                                             |
| SubscriberVpcVpnTable     | SubscriberVpcVpnTable                                                         |
| SubscriberConfig          | SubscriberConfig                                                              |
| ServiceToken              | arn:aws:lambda:us-east-1:987654321:function:initializeDynamo                  |
| TransitAssumeRoleArn      | arn:aws:iam::12345667489:role/TransitAssumeRole                               |

##### SubscriberQueue (DynamoDB Table)

##### Subscriber State machine

### Rebalance mechanism
