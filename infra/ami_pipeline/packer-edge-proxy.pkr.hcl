# Declarative Packer template for baking Atlassian Sovereign Envoy Proxy Golden AMI
# Video chapter: 17:45 - Creating the machine image (AMI) & AWS Infrastructure

packer {
  required_plugins {
    amazon = {
      version = ">= 1.2.8"
      source  = "github.com/hashicorp/amazon"
    }
  }
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "image_version" {
  type    = string
  default = "2.4.0-sovereign"
}

source "amazon-ebs" "envoy_golden_ami" {
  ami_name      = "sovereign-envoy-golden-ami-${var.image_version}-{{timestamp}}"
  instance_type = "c6i.2xlarge"
  region        = var.region

  source_ami_filter {
    filters = {
      name                = "ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"
      root-device-type    = "ebs"
      virtualization-type = "hvm"
    }
    most_recent = true
    owners      = ["099720109477"] # Canonical
  }

  ssh_username = "ubuntu"

  tags = {
    Name        = "Sovereign-Envoy-Golden-AMI"
    Version     = var.image_version
    ManagedBy   = "Sovereign-Edge-Pipeline"
    Environment = "production"
    Hardened    = "true"
  }
}

build {
  sources = ["source.amazon-ebs.envoy_golden_ami"]

  # Provision SaltStack states and system configuration
  provisioner "shell" {
    inline = [
      "echo '==> Updating packages and installing Salt minion'",
      "sudo apt-get update -y && sudo apt-get install -y curl salt-minion",
      "sudo mkdir -p /srv/salt"
    ]
  }

  provisioner "file" {
    source      = "salt-states/"
    destination = "/tmp/salt-states"
  }

  provisioner "shell" {
    inline = [
      "sudo mv /tmp/salt-states/* /srv/salt/",
      "echo '==> Executing SaltStack state highstate for Envoy & Kernel tuning'",
      "sudo salt-call --local state.apply envoy",
      "echo '==> Cleaning up build artifacts and zeroing disk'",
      "sudo rm -rf /tmp/* /var/log/*.log",
      "sudo history -c"
    ]
  }
}
