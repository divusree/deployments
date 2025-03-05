# deployments

## Setup

1. Install the required Python packages:
    ```sh
    pip install -r requirements.txt
    ```

2. Ensure your docker image is already pushed and your security groups and ami creds are configured. 

## Usage

### Creating and Managing EC2 Instances

1. Create an EC2 instance and deploy the Docker container:
    ```python
    from deployment import InstanceManagement

    instance_config = {
        "REGION": "us-east-1",
        "INSTANCE_TYPE": "t3.micro",
        "KEY_NAME": "my-key-pair",
        "SECURITY_GROUP_ID": "sg-0123",
        "AMI_ID": "ami-0123",
        "CONTAINER_NAME": "model",
        "EXPOSED_PORT": 5000,
        "AWS_USER": "ec2-user",
        "KEY_PATH": "mypem.pem"
    }

    ECR_REPO = "ecr_docker_tag/myrepo:latest"
    nginx_config = {
        "subdomains": ["api.example.com", "www.api.example.com"],
        "endpoint": "myendpoint"
    }

    manager = InstanceManagement(instance_config)
    instance_id, url = manager.create_instance_with_repo_and_endpoint(instance_config, ECR_REPO, nginx_config)
    print(f"Instance ID: {instance_id}, URL: {url}")
    ```

2. Start an existing EC2 instance:
    ```python
    manager.start_instance(instance_id)
    ```

2.1 Pull another image into an existing instance: 
    manager = InstanceManagement(instance_config)
    manager.start_instance(instance_id)
    manager.pull_image_and_run(ECR_REPO)
    manager.nginx_setup(nginx_config)      

3. Stop an EC2 instance:
    ```python
    manager.stop_instance(instance_id)
    ```

### Testing

1. Test the deployed API via the public URL:
    ```python
    response = requests.get("http://www.example.com/myendpoint", json={"payload": payload})
    print(response.json())
    