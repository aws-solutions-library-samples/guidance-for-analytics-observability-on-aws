from enum import Enum
from typing import Optional

from aws_cdk.aws_opensearchservice import CfnDomain


class TshirtSize(Enum):
    XS = 'xs'
    S = 's'
    M = 'm'
    L = 'l'
    XL = 'xl'


class ClusterConfig:

    def __init__(self, size: TshirtSize, **kwargs) -> None:
        if size == TshirtSize.XS:
            self._cluster_config = CfnDomain.ClusterConfigProperty(
                dedicated_master_enabled=False,
                instance_count=3,
                instance_type="t3.small.search",
                warm_enabled=False,
                zone_awareness_enabled=False
            )
            self._ebs_config = CfnDomain.EBSOptionsProperty(
                ebs_enabled=True,
                volume_size=10,
                volume_type="gp3"
            )
        elif size == TshirtSize.S:
            self._cluster_config = CfnDomain.ClusterConfigProperty(
                dedicated_master_enabled=False,
                instance_count=3,
                instance_type="m6g.large.search",
                warm_enabled=False,
                zone_awareness_config=CfnDomain.ZoneAwarenessConfigProperty(
                    availability_zone_count=3
                ),
                zone_awareness_enabled=True
            )
            self._ebs_config = CfnDomain.EBSOptionsProperty(
                ebs_enabled=True,
                volume_size=80,
                volume_type="gp3"
            )
        elif size == TshirtSize.M:
            self._cluster_config = CfnDomain.ClusterConfigProperty(
                dedicated_master_count=3,
                dedicated_master_enabled=True,
                dedicated_master_type="c6g.large.search",
                instance_count=3,
                instance_type="r6g.xlarge.search",
                warm_count=1,
                warm_enabled=True,
                warm_type="ultrawarm1.medium.search",
                zone_awareness_config=CfnDomain.ZoneAwarenessConfigProperty(
                    availability_zone_count=3
                ),
                zone_awareness_enabled=True
            )
            self._ebs_config = CfnDomain.EBSOptionsProperty(
                ebs_enabled=True,
                volume_size=600,
                volume_type="gp3"
            )
        elif size == TshirtSize.L:
            self._cluster_config = CfnDomain.ClusterConfigProperty(
                dedicated_master_count=3,
                dedicated_master_enabled=True,
                dedicated_master_type="c6g.xlarge.search",
                instance_count=3,
                instance_type="r6g.4xlarge.search",
                warm_count=1,
                warm_enabled=True,
                warm_type="ultrawarm1.large.search",
                zone_awareness_config=CfnDomain.ZoneAwarenessConfigProperty(
                    availability_zone_count=3
                ),
                zone_awareness_enabled=True
            )
            self._ebs_config = CfnDomain.EBSOptionsProperty(
                ebs_enabled=True,
                volume_size=4096,
                volume_type="gp3"
            )
        else:
            self._cluster_config = CfnDomain.ClusterConfigProperty(
                dedicated_master_count=5,
                dedicated_master_enabled=True,
                dedicated_master_type="c6g.2xlarge.search",
                instance_count=12,
                instance_type="r6.4xlarge.search",
                warm_count=4,
                warm_enabled=True,
                warm_type="ultrawarm1.large.search",
                zone_awareness_config=CfnDomain.ZoneAwarenessConfigProperty(
                    availability_zone_count=3
                ),
                zone_awareness_enabled=True
            )
            self._ebs_config = CfnDomain.EBSOptionsProperty(
                ebs_enabled=True,
                volume_size=4096,
                volume_type="gp3"
            )

    def load_tshirt_size(size: Optional[str]):
        if size is None:
            raise Exception("TshirtSize parameter for Opensearch domain is required")
        elif size.lower() == 'xs':
            return TshirtSize.XS
        elif size.lower() == 's':
            return TshirtSize.S
        elif size.lower() == 'm':
            return TshirtSize.M
        elif size.lower() == 'l':
            return TshirtSize.L
        elif size.lower() == 'xl':
            return TshirtSize.XL
        else:
            raise Exception("TshirtSize parameter must be XS, S, M, L or XL")

    @property
    def cluster_config(self):
        return self._cluster_config

    @property
    def ebs_config(self):
        return self._ebs_config
