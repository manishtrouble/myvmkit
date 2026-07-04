provider "hcloud" {}

locals {
  ssh_public_key = trimspace(file(pathexpand(var.ssh_public_key_path)))

  base_labels = {
    role    = "devbox"
    managed = "terraform"
  }
}

resource "hcloud_ssh_key" "personal" {
  name       = "${var.name}-${var.username}"
  public_key = local.ssh_public_key
}

resource "hcloud_firewall" "devbox" {
  name = "${var.name}-tailscale-only"

  dynamic "rule" {
    for_each = toset(var.allow_public_ssh_cidrs)

    content {
      direction  = "in"
      protocol   = "tcp"
      port       = "22"
      source_ips = [rule.value]
    }
  }

  rule {
    direction       = "out"
    protocol        = "tcp"
    port            = "any"
    destination_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction       = "out"
    protocol        = "udp"
    port            = "any"
    destination_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction       = "out"
    protocol        = "icmp"
    destination_ips = ["0.0.0.0/0", "::/0"]
  }
}

resource "hcloud_server" "devbox" {
  name        = var.name
  image       = var.image
  server_type = var.server_type
  location    = var.location

  ssh_keys     = [hcloud_ssh_key.personal.id]
  firewall_ids = [hcloud_firewall.devbox.id]

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    username                = var.username
    hostname                = var.name
    ssh_public_key          = local.ssh_public_key
    tailscale_auth_key      = var.tailscale_auth_key
    dotfiles_repo_url       = var.dotfiles_repo_url
    dotfiles_bootstrap_path = var.dotfiles_bootstrap_path
  })

  labels = merge(local.base_labels, var.labels)
}
