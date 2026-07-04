# myvmkit

> Repeatable Hetzner devbox provisioning with Terraform, cloud-init, Tailscale-only SSH, and bootstrapped zsh/Neovim/tmux/yazi dotfiles.

## What it creates

`myvmkit` provisions a Hetzner Cloud VM and configures it as a personal development box.

It uses:

- Terraform for Hetzner infrastructure;
- a small selector script to choose a Hetzner server type/location;
- cloud-init for first-boot setup;
- Tailscale for private SSH access;
- UFW for host firewall hardening;
- this repo's `dotfiles/` for shell/editor/tmux/yazi setup.

Normal access is over Tailscale, not public SSH.

## Prerequisites

Install locally:

- Terraform
- Python 3
- a Hetzner Cloud API token with read/write access to the intended project
- a Tailscale auth key
- an SSH keypair on your Mac/workstation

For this setup, the SSH public key is read from your local machine and installed on the VM. The private key never goes into Terraform.

## Local secrets

Create a local `.env` file. It is gitignored.

```bash
export HCLOUD_TOKEN="your-hetzner-token"
export TF_VAR_tailscale_auth_key="your-tailscale-auth-key"
```

Use a one-off/pre-authorized Tailscale auth key for the first VM. Do not commit `.env`.

## Local Terraform values

Create a local tfvars file. It is gitignored.

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
```

## Create the first VM

Load local secrets automatically through `make` or manually with `source .env`.

Dry-run the VM selector:

```bash
make choose-vm-dry-run \
  NAME=devbox1 \
  MIN_CPU=2 \
  MIN_RAM=4 \
  MAX_EUR=8 \
  LOCATIONS=fsn1,nbg1,hel1
```

Write the selected server type/location:

```bash
make choose-vm \
  NAME=devbox1 \
  MIN_CPU=2 \
  MIN_RAM=4 \
  MAX_EUR=8 \
  LOCATIONS=fsn1,nbg1,hel1
```

Then run Terraform:

```bash
make init
make plan
make apply
```

After apply, wait for cloud-init to finish and for the node to appear in Tailscale.

Connect:

```bash
make ssh
```

or:

```bash
ssh youruser@devbox1
```

## Dotfiles bootstrap

On first boot, cloud-init clones this repo and runs:

```bash
dotfiles/bootstrap.sh
```

The bootstrap script installs or links:

- Oh My Zsh
- Powerlevel10k
- zsh autosuggestions and syntax highlighting
- Neovim config with lazy.nvim plugins
- yazi and `ya`
- tmuxp session file

After SSH, you can start the standard layout with:

```bash
nvim-omp-term
```

This starts the `dotfiles/tmuxp/nvim-omp-term.yaml` tmuxp layout and defaults the tmux session name to the current directory basename.

## Multiple VMs

The current Terraform model manages one VM per Terraform workspace/state.

For a second VM:

```bash
terraform -chdir=terraform workspace new devbox2

make choose-vm \
  NAME=devbox2 \
  CHOOSE_VM_OUTPUT=terraform/devbox2.tfvars.json

make plan TFVARS=devbox2.tfvars.json
make apply TFVARS=devbox2.tfvars.json
```

Do not just change `name` in the same workspace unless you intend to replace the existing VM.

## Troubleshooting

On the VM, check cloud-init logs:

```bash
sudo tail -200 /var/log/cloud-init-output.log
sudo tail -200 /var/log/devbox-firstboot.log
```

Check Tailscale:

```bash
sudo tailscale status
```

Check UFW:

```bash
sudo ufw status verbose
```

## Destroy

Destroy the VM in the current workspace:

```bash
make destroy
```

If using per-VM tfvars:

```bash
make destroy TFVARS=devbox2.tfvars.json
```
