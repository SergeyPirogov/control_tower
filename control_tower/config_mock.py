

class Config(object):
    def __init__(self, container="getcarrier/perfmeter:latest",
                 execution_params={"cmd": "-n -t /mnt/jmeter/FloodIO.jmx "
                                          "-JVUSERS=10 -JDURATION=120 -JRAMP_UP=1 -Jtest_name=test"},
                 job_type="free_style", job_name="test", concurrency=1, groupid=None):
        self.container = container
        self.execution_params = execution_params
        self.job_type = job_type
        self.job_name = job_name
        self.concurrency = concurrency
        self.groupid = groupid

    def get_config(self):
        return dict(container=self.container,
                    execution_params=self.execution_params,
                    job_type=self.job_type,
                    job_name=self.job_name,
                    concurrency=self.concurrency,
                    groupid=self.groupid)


class BulkConfig(object):
    def __init__(self, bulk_container, bulk_params, job_type, job_name, bulk_concurrency, channel=[],
                 bucket="", artifact="", save_reports=None, junit=False, quality_gate=False):
        self.container = bulk_container
        self.execution_params = bulk_params
        self.job_name = job_name
        self.concurrency = bulk_concurrency
        self.job_type = job_type
        self.channel = channel
        self.bucket = bucket
        self.artifact = artifact
        self.save_reports = save_reports
        self.junit = junit
        self.quality_gate = quality_gate

    def get_config(self):
        return dict(container=self.container,
                    execution_params=self.execution_params,
                    job_type=self.job_type,
                    job_name=self.job_name,
                    concurrency=self.concurrency,
                    channel=self.channel,
                    bucket=self.bucket,
                    artifact=self.artifact,
                    save_reports=self.save_reports,
                    junit=self.junit,
                    quality_gate=self.quality_gate)
