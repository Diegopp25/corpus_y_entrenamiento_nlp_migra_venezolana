terraform {
  required_version = ">= 1.5.0"

  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.0"
    }
  }
}

provider "digitalocean" {}

variable "region" {
  description = "DigitalOcean region for the Droplet."
  type        = string
  default     = "nyc3"
}

variable "size" {
  description = "Droplet size; 4 GB RAM is a practical minimum for this model."
  type        = string
  default     = "s-2vcpu-4gb"
}

variable "ssh_key_fingerprints" {
  description = "Fingerprints of SSH keys already added to your DigitalOcean account."
  type        = list(string)
}

resource "digitalocean_droplet" "cultural_bias_api" {
  name     = "cultural-bias-api"
  region   = var.region
  size     = var.size
  image    = "ubuntu-24-04-x64"
  ssh_keys = var.ssh_key_fingerprints
  tags     = ["cultural-bias"]
}

output "droplet_ipv4" {
  description = "Public IPv4 address of the Droplet."
  value       = digitalocean_droplet.cultural_bias_api.ipv4_address
}
