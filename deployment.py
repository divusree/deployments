import boto3
import paramiko
import time
import crossplane


class InstanceManagement:
    def __init__(self, config):
        self.config = config
        self.instance_id = None
        self.public_dns = None
        self.ssh = None
        self.ec2_client = boto3.client("ec2", region_name=self.config["REGION"])
        self.ecr_client = boto3.client("ecr", region_name=self.config["REGION"])        
    # Create EC2 instance
    def create_instance(self):
        print("Creating EC2 instance...")
        instances = self.ec2_client.run_instances(
            ImageId=self.config["AMI_ID"],
            InstanceType=self.config["INSTANCE_TYPE"],
            KeyName=self.config["KEY_NAME"],
            SecurityGroupIds=[self.config["SECURITY_GROUP_ID"]],
            MinCount=1,
            MaxCount=1,
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': 'ECR-Image-Puller'
                        }
                    ]
                }
            ]
        )

        instance_id = instances['Instances'][0]['InstanceId']
        print(f"Instance {instance_id} created. Waiting for it to be in running state...")

        waiter = self.ec2_client.get_waiter('instance_running')
        waiter.wait(InstanceIds=[instance_id])

        print(f"Instance {instance_id} is now running.")
        self.instance_id = instance_id

        self.public_dns, self.public_ip = self.get_instance_public_ip_info(instance_id)
        return instance_id
    def start_instance(self, instance_id):
        print("Starting EC2 instance...")
        self.ec2_client.start_instances(InstanceIds=[instance_id])
        print(f"Instance {instance_id} started. Waiting for it to be in running state...")

        waiter = self.ec2_client.get_waiter('instance_running')
        waiter.wait(InstanceIds=[instance_id])
        self.instance_id = instance_id
        self.public_dns, self.public_ip  = self.get_instance_public_ip_info(instance_id)
        self.connect()
        return True

    def stop_instance(self, instance_id):
        if self.ssh:
            self.ssh.close()
        print("Stopping EC2 instance...")
        self.ec2_client.stop_instances(InstanceIds=[instance_id])
        print(f"Instance {instance_id} stopped. Waiting for it to be in stopped state...")

        waiter = self.ec2_client.get_waiter('instance_stopped')
        waiter.wait(InstanceIds=[instance_id])
        return True
        
    # Get the instance's public DNS
    def get_instance_public_ip_info(self, instance_id):
        response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
        public_dns = response['Reservations'][0]['Instances'][0]['PublicDnsName']
        public_ip = response['Reservations'][0]['Instances'][0]['PublicIpAddress']
        return public_dns, public_ip 
    
    # Get ECR authentication token
    def get_ecr_login(self):
        response = self.ecr_client.get_authorization_token()
        auth_data = response['authorizationData'][0]
        token = auth_data['authorizationToken']
        registry = auth_data['proxyEndpoint']
        return token, registry

    def connect(self):
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(self.public_dns, username=self.config["AWS_USER"], key_filename=self.config["KEY_PATH"])
        return self.ssh
    
    # Execute commands via SSH
    def execute_ssh_commands(self, commands):
        self.connect()

        for command in commands:
            print(f"Executing: {command}")
            stdin, stdout, stderr = self.ssh.exec_command(command)
            print(stdout.read().decode())
            print(stderr.read().decode())
            print(f"{command} complete")
            print("-"*30)

    
    def pull_image_and_run(self, PRIVATE_ECR_REPO): 
        token, registry = self.get_ecr_login()
        # docker_login_cmd = f"echo {token} | docker login --username AWS --password-stdin {registry}"
        docker_login_cmd = f'aws ecr get-login-password --region {self.config["REGION"]} | sudo docker login --username AWS --password-stdin {registry} '

        commands = [
            "sudo yum update -y",
            "sudo yum install -y docker nginx",
            "sudo service docker start",
            "sudo usermod -a -G docker ec2-user",
            docker_login_cmd,
            f"sudo docker pull {PRIVATE_ECR_REPO}",
            f"sudo docker run -d --name {self.config["CONTAINER_NAME"]} -p {self.config["EXPOSED_PORT"]}:5000 {PRIVATE_ECR_REPO}"
        ]

        self.execute_ssh_commands(commands)
        print(f"Private ECR image {PRIVATE_ECR_REPO} pulled and running as a container on instance {self.instance_id}.")
    
        return True
    
    def nginx_setup(self, nginx_config):   
        subdomains = ' '.join(nginx_config["subdomains"])
        endpoint = nginx_config["endpoint"]
        config = {"config":[{"parsed": [{
                "directive": "server",
                "args": [],
                "block": [{"directive": "listen","args": ["80"]},
                          {"directive": "listen","args": ["[::]:80"]},
                          {"directive": "server_name","args": subdomains},
                          {"directive": "location","args": ["/" + endpoint],
                           "block":[{"directive": "proxy_pass","args": ["http://127.0.0.1:5000/{}".format(endpoint)]},
                                    {"directive": "proxy_set_header","args": ["Host \$host"]},
                                    {"directive": "proxy_set_header","args": ["X-Real-IP \$remote_addr"]},
                                    {"directive": "proxy_set_header","args": ["X-Forwarded-For \$proxy_add_x_forwarded_for"]},
                                    {"directive": "proxy_set_header","args": ["X-Forwarded-Proto \$scheme"]}]},]}],
                            "file": "nginx_config.conf"}]}
        print("Creating nginx config at /etc/nginx/conf.d/nginx_config.conf")
        crossplane.builder.build_files(config,indent=4, tabs=False, dirname = '/etc/nginx/conf.d/')
        self.connect()
        self.execute_ssh_commands(["sudo systemctl start nginx"])
        url = "".join ([nginx_config["subdomains"][0],"/",nginx_config["endpoint"]])
        print(f'nginx set up complete. please test at {url}')
        return url
    def create_instance_with_repo_and_endpoint(self, instance_config, ECR_REPO, nginx_config):
        instance_id = self.create_instance(instance_config)
        print("instance_id = ", instance_id)
        self.pull_image_and_run(ECR_REPO)
        url = self.nginx_setup(nginx_config)        
        return instance_id, url