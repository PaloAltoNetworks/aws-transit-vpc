This document talks about AWS Lambda functions that are implemented.

## CloudTrailLambda
  * Triggerd when Object:Put on CloudTrail S3 bucket
  * Looks for events ['CreateVpc', 'DeleteVpnConnection']
  * Sends notification to Subscriber SNS Topic

## SubscriberDeciderLambda:
  * This function will get triggered by Subscriber SNS Topic
  * Receives the message and sends it to SQS queue
  * Starts the State Machine if the State Machine is not running, if it is running exit the process

## TransitDeciderLambda:
  * This function will get triggered by Transit SNS Topic
  * Receives the message and sends it to SQS queue
  * Starts the State Machine if the State Machine is not running, if it is running exit the process

## InitializeSubscriberDynamoTablesLambda:
  * This function will get created and triggered by subscriber CFT
  * Gets the subscriber config table and resource ids from CFT and updates the table with resource information.

## InitializeTransitDynamoTablesLambda
  * This function will get created and triggered by Transit CFT, required parameters will get passed from CFT.
  * Update the assume role
    * Gets the asumerole name and subscriber AWS account number then adds the account number in the assume role policy.
  * Update BGP tunnel pool IP
    * It downloads the available CIDR range for VPN and enters the values into DynamoDB table.
  * Update Transit config table
    * Gets the the table name and resources ids from CFT and updates the config DynamoDB table with the resources information.
  * Update PA group information
    * Gets the PAGroup info table name from the CFT and updates the table with PaGroup{id}, N1Asn and N2Asn numbers.
  * Update VGW ASN
    * Gets the DynamoDB VgwAsn table and updates the table with privat ASN numbers between 64512-64612
    
##  FetchFromSubscriberQueueLambda:
  * Get one message from SQS queue
  * Based on the 'Action' value it will trigger that specific action related Lambda Function (ie., CreateVpc, ConfigureSubscribingVpcVpn,VpnConfigured etc.,)

## CreateVpcLambda:
  * Checks whether the VPC is subscribing VPC or not
  * If subsribing VPC, updates Subscriber LocalDB with VpcId and VpcCidr, if the VpcCidr is not conflicts with existing DB-Items.
    * Then sends notification to Transit SNS with 'Action': 'FetchVpnServerDetails'
  * If not exit the process

## FetchVpnServerDetailsLambda:
  * Checks for Vpc Cidr conflicts, if no conflicts proceed else exit from the process
  * Checks for Available VGW Asns, if available proceed else exit from the process
  * Checks for Available PA Groups, if PA Groups are not present, returns an 'Action' with 'CreateNewPaGroup' to CreateNewPaGroupLambda
      * Then sends the message back to SQS queue, to process it once the creation of New PA group is done, then exit from process
  * Checks for Available BgpTunnelIpPools, if available proceed else exit the process
  * If something fails in the above process, it will send notification to Subscriber SNS with 'Action': 'VpnFailed'
  * If everything goes fine, it will send notification to Subscriber SNS with 'Action': 'ConfigureSubscribingVpcVpn'
      * Updates the Transit-PaGroupInfo table with N1Eip, N1Mgmt, N1Pip, N2Eip, N2Mgmt, N2Pip, StackRegion
      * Updates the Transit-BgpTunnelIpPools with Available=NO, VpcId and PaGroupName
      * Updates the Transit-VgwAsn table with InUse=YES, VpcCidr, and VpcId

## CreateNewPaGroupLambda:
  * Creates New PaGroup with Cloud formation template (CFT)
  * Send CFT stack name to CheckStatusLambda

## CheckStackStatusLambda:
  * Checks for the Status complete of New PA Group cloud formation stack
  * Once Stack completed, it will check for the status of PA Group Servers (PA Server takes around 5-10 to come up)
  * Once PA Server status is ready, it will bootstrap the PA Servers

## ConfigureSubscribingVpcVpnLambda:
  * It will create VGW, CGW1, CGW2 if they are not created before and, creates VPN1 and VPN2
  * Updates the Subscriber LocalDB with VGW, CGW1, CGW2, VPN1 and VPN2
  * Updates Subscriber VpcVpnTable with VPNId, VPCId and PaGroup
  * If everything goes well, it will send notification to Transit SNS with 'Action': 'ConfigureTransitVpn'
  * If something fails, it will send notification to Transit SNS wiht 'Action': 'SubscriberVpnConfigurationFailed'

## ConfigureTransitVpnLambda:
  * It will create the VPN connections with the PA Group servers
  * Checks for the status of the VPN connections, if the connections failed to establish it will send notification to Subscriber SNS Toic with 'Action':'VpnFailed'
      * update the Transit-PaGroupInfo table VpcCount to -1
      * update the Transit-VpcVpnTable status to Failed
      * update the Transit-BgpTunnelIpPools talbe with Available=YES
  * If the VPN connections are established, it will update Transit PaGroupInfo table with VpcCount +1
      * update the Transit-PaGroupInfo table VpcCount to +1
      * update the Transit VpcTable with VpcId, CurrentStatus, IpSegment, Node1VpnId, Node2VpnId, PaGroupName, Region, SubscriberAssumeRoleArn, SubscriberSnsArn, VpcCidr, vpc-xxxxx

## SubscriberVpnConfigurationFailedLambda:
  * update the Transit-PaGroupInfo table VpcCount to -1
  * update the Transit-BgpTunnelIpPools talbe with Available=YES

## VpnConfiguredLambda:
  * updates the tags for VPC
        Key                 Value
        ConfigStatus        VPN-Configured
        ConfigReason        Active

## VpnFailedLambda:
  * updates the tags for VPC
        Key                 Value
        ConfigStatus        VPN-Failed
        ConfigReason        The actual reason

## DeleteVpnConnectionLambda:
  * Deletes two vpn connections associated with the VPC
  * Deletes the entry from the Subscriber Local DB which has the deteted VPN connections
  * Deletes VPN entries from the Subscriber VpcVpnTable
  * Sends notification to Transit SNS Topic with 'Action': 'DeleteTransitVpnConfiguration'

## DeleteTransitVpnConfigurationLambda:
  * Deletes the VPN connections with the PA Servers
  * Updates the Transit-PaGroupInfo table with VpcCount to -1
  * Updates the Transit-BgpTunnelIpPools table with Available= YES
  * Deletes entry from Transit-VpcTable

## RebalancePaGroupsLambda:
  * Scans the Transit-PaGroupInfo table to get the PaGroups which are InUse and lessthan PaGroupCapacity(<4) for the rebalancing
  * Passes results to the rebalancing function, which will return two PaGropus, ToPaGroup and FromPaGroup (means moving VPN connection from FromPaGroup to ToPaGroup)
  * Sends notification to Subscriber SNS Topic with 'Action': 'ConfigureSubscribingVpcVpn'

## TransitTaskHandlerLambda:
  * Reads from Priority queue, if it receives any message, it reads the 'Action' in message then triggers the Lambda which is associated with the Action ['ConfiugreTransitVpn', 'FetchVpnServerDetails', 'SubscriberConfigurationFailed', 'ReabalancePaGroups', 'DeleteTransitVpnConfiguration', 'CheckStackStatus', 'CreateNewPaGroup']
  * if nothing returned from Priority Queue it will, check for the Rebalance Operation

