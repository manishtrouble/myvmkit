output "server_id" {
  description = "Hetzner server ID."
  value       = hcloud_server.devbox.id
}

output "server_name" {
  description = "Hetzner server name."
  value       = hcloud_server.devbox.name
}

output "ipv4_address" {
  description = "Public IPv4 address. Used for break-glass/debugging; normal SSH should use Tailscale."
  value       = hcloud_server.devbox.ipv4_address
}

output "ipv6_address" {
  description = "Public IPv6 address. Used for break-glass/debugging; normal SSH should use Tailscale."
  value       = hcloud_server.devbox.ipv6_address
}

output "tailscale_ssh_hint" {
  description = "SSH hint assuming Tailscale MagicDNS hostname matches var.name."
  value       = "ssh ${var.username}@${var.name}"
}
