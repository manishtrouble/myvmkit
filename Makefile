TF_DIR := terraform
PYTHON ?= python3
TERRAFORM ?= terraform

# Optional local secrets file. This file is gitignored.
# Expected keys: HCLOUD_TOKEN and TF_VAR_tailscale_auth_key.
-include .env
export HCLOUD_TOKEN
export TF_VAR_tailscale_auth_key

MIN_CPU ?= 2
MIN_RAM ?= 4
MAX_EUR ?= 8
LOCATIONS ?= fsn1,nbg1,hel1
PREFERRED_LOCATIONS ?=
PREFERRED_FAMILIES ?=
ARCHITECTURE ?= x86
CPU_TYPE ?=
PRICE_KIND ?= gross
NAME ?= devbox-$(shell date +%Y-%m-%d)
CHOOSE_VM_OUTPUT ?= $(TF_DIR)/terraform.auto.tfvars.json
TFVARS ?=
TFVARS_ARG := $(if $(strip $(TFVARS)),-var-file=$(TFVARS),)

CHOOSE_VM_ARGS := \
	--name "$(NAME)" \
	--min-cpu "$(MIN_CPU)" \
	--min-ram "$(MIN_RAM)" \
	--max-eur "$(MAX_EUR)" \
	--locations "$(LOCATIONS)" \
	--architecture "$(ARCHITECTURE)" \
	--price-kind "$(PRICE_KIND)" \
	--output "$(CHOOSE_VM_OUTPUT)"

ifneq ($(strip $(PREFERRED_LOCATIONS)),)
CHOOSE_VM_ARGS += --preferred-locations "$(PREFERRED_LOCATIONS)"
endif

ifneq ($(strip $(PREFERRED_FAMILIES)),)
CHOOSE_VM_ARGS += --preferred-families "$(PREFERRED_FAMILIES)"
endif

ifneq ($(strip $(CPU_TYPE)),)
CHOOSE_VM_ARGS += --cpu-type "$(CPU_TYPE)"
endif

.PHONY: choose-vm choose-vm-dry-run init fmt validate plan apply ssh destroy devbox

choose-vm:
	$(PYTHON) scripts/choose-vm.py $(CHOOSE_VM_ARGS)

choose-vm-dry-run:
	$(PYTHON) scripts/choose-vm.py $(CHOOSE_VM_ARGS) --dry-run

init:
	$(TERRAFORM) -chdir=$(TF_DIR) init

fmt:
	$(TERRAFORM) -chdir=$(TF_DIR) fmt

validate:
	$(TERRAFORM) -chdir=$(TF_DIR) validate

plan:
	$(TERRAFORM) -chdir=$(TF_DIR) plan $(TFVARS_ARG)

apply:
	$(TERRAFORM) -chdir=$(TF_DIR) apply $(TFVARS_ARG)

ssh:
	@cmd="$$($(TERRAFORM) -chdir=$(TF_DIR) output -raw tailscale_ssh_hint)"; \
	printf '%s\n' "$$cmd"; \
	exec $$cmd

destroy:
	$(TERRAFORM) -chdir=$(TF_DIR) destroy $(TFVARS_ARG)

devbox: choose-vm init apply
	@printf 'Devbox created. Run: make ssh\n'
