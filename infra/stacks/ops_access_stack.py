"""POC / Ops Access – SSM-only bastion for private Aurora access.

Operational access only (psql, migrations, debugging).
Remove or restrict for production.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aws_cdk import CfnOutput, Fn, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from constructs import Construct

if TYPE_CHECKING:
    from infra.stacks.foundation_stack import FoundationStack


class OpsAccessStack(Stack):
    """POC / Ops Access – SSM bastion host for private Aurora."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        foundation: FoundationStack,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc: ec2.IVpc = foundation.vpc
        aurora_sg: ec2.ISecurityGroup = foundation.aurora_sg
        bastion_sg: ec2.ISecurityGroup = foundation.bastion_sg

        region: str = self.region or "us-east-1"

        # POC / Ops Access – Aurora: allow PostgreSQL from bastion (SG in FoundationStack)
        aurora_sg.add_ingress_rule(
            bastion_sg,
            ec2.Port.tcp(5432),
            "Allow SSM bastion access (POC / Ops)",
        )

        # POC / Ops Access – VPC endpoints for SSM (no NAT/internet required)
        endpoints_sg: ec2.SecurityGroup = ec2.SecurityGroup(
            self,
            "EndpointsSg",
            vpc=vpc,
            description="POC / Ops Access - VPC endpoints for SSM. Remove for prod.",
            allow_all_outbound=True,
        )
        endpoints_sg.add_ingress_rule(
            bastion_sg,
            ec2.Port.tcp(443),
            "HTTPS from bastion (POC / Ops)",
        )

        ssm_endpoint: ec2.InterfaceVpcEndpoint = ec2.InterfaceVpcEndpoint(
            self,
            "SsmEndpoint",
            vpc=vpc,
            service=ec2.InterfaceVpcEndpointService(
                f"com.amazonaws.{region}.ssm", port=443
            ),
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[endpoints_sg],
            private_dns_enabled=True,
        )
        ec2_endpoint: ec2.InterfaceVpcEndpoint = ec2.InterfaceVpcEndpoint(
            self,
            "Ec2MessagesEndpoint",
            vpc=vpc,
            service=ec2.InterfaceVpcEndpointService(
                f"com.amazonaws.{region}.ec2messages", port=443
            ),
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[endpoints_sg],
            private_dns_enabled=True,
        )
        ssm_messages_endpoint: ec2.InterfaceVpcEndpoint = ec2.InterfaceVpcEndpoint(
            self,
            "SsmMessagesEndpoint",
            vpc=vpc,
            service=ec2.InterfaceVpcEndpointService(
                f"com.amazonaws.{region}.ssmmessages", port=443
            ),
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[endpoints_sg],
            private_dns_enabled=True,
        )

        # POC / Ops Access – IAM role for SSM Session Manager
        bastion_role: iam.Role = iam.Role(
            self,
            "BastionRole",
            role_name="integrationhub-ssm-role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="POC / Ops Access - SSM bastion role. Remove for prod.",
        )
        bastion_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "AmazonSSMManagedInstanceCore"
            )
        )

        # POC / Ops Access – EC2 bastion (no SSH, no public IP, no key pair)
        bastion_instance: ec2.Instance = ec2.Instance(
            self,
            "Bastion",
            instance_name="integrationhub-ssm-bastion",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.MICRO
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_group=bastion_sg,
            role=bastion_role,
            allow_all_outbound=True,
            associate_public_ip_address=False,
        )
        bastion_instance.node.add_dependency(ssm_endpoint)
        bastion_instance.node.add_dependency(ec2_endpoint)
        bastion_instance.node.add_dependency(ssm_messages_endpoint)

        # Outputs
        CfnOutput(
            self,
            "BastionInstanceId",
            value=bastion_instance.instance_id,
            description="POC / Ops - SSM bastion instance ID",
            export_name="ops-bastion-instance-id",
        )
        CfnOutput(
            self,
            "BastionSecurityGroupId",
            value=bastion_sg.security_group_id,
            description="POC / Ops - Bastion security group ID",
            export_name="ops-bastion-sg-id",
        )
        CfnOutput(
            self,
            "VpcEndpointIds",
            value=Fn.join(
                ",",
                [
                    ssm_endpoint.vpc_endpoint_id,
                    ec2_endpoint.vpc_endpoint_id,
                    ssm_messages_endpoint.vpc_endpoint_id,
                ],
            ),
            description="POC / Ops - SSM VPC endpoint IDs (ssm,ec2messages,ssmmessages)",
            export_name="ops-vpc-endpoint-ids",
        )
