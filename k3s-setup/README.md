# K3s Cluster Setup

## Nodes
| Hostname | IP | Role |
|----------|-----|------|
| heimdall | 10.0.20.160 | K3s server (control plane) |
| bestla | 10.0.20.161 | K3s agent (worker) |
| mimir | 10.0.20.162 | K3s agent (worker) |

**NFS Storage:** UniFi drive at 10.0.15.15

---

## Step 1: Prepare Autoinstall USBs

### Generate password hash (on your Mac)
```bash
# (Python's crypt module was removed in Python 3.13; use openssl instead)
openssl passwd -6    # prompts for the password, prints a $6$... SHA-512 hash
```

### Get your SSH public key
```bash
cat ~/.ssh/id_ed25519.pub
# If you don't have one: ssh-keygen -t ed25519
```

> The nodes only accept SSH keys (password auth is off). Every machine that should reach
> them needs its public key in `~vaishak/.ssh/authorized_keys` on all three nodes, and in
> the autoinstall `user-data` files so reinstalls keep it. Ansible uses
> `ansible_ssh_private_key_file` in `ansible/inventory/hosts.yml`; point it at the key you
> actually have (it defaults to `~/.ssh/id_rsa`).
>
> To add a new machine: copy its `~/.ssh/id_ed25519.pub` to a machine that already has
> access, then from there run (for `.160`, `.161` and `.162`):
> `ssh vaishak@10.0.20.160 'cat >> ~/.ssh/authorized_keys' < new-machine.pub`

### Edit each user-data file
Fill in `REPLACE_WITH_HASHED_PASSWORD` and `REPLACE_WITH_YOUR_PUBLIC_KEY` in:
- `autoinstall/heimdall/user-data`
- `autoinstall/bestla/user-data`
- `autoinstall/mimir/user-data`

### ⚠️ Check ethernet interface name
Dell Optiplex interface names vary. Common options:
- `eno1` (most common on Optiplex)
- `enp1s0`
- `enp2s0`

If you're unsure, boot a live Ubuntu USB first and run `ip link show`.
Update the interface name in each `user-data` file if needed.

### Flash USBs with Balena Etcher
1. Download Ubuntu Server 24.04 LTS: https://ubuntu.com/download/server
2. Flash to USB with Balena Etcher: https://etcher.balena.io
3. After flashing, mount the USB and copy autoinstall files:

```bash
# After flashing, USB has a partition called "CIDATA" or you need to add files
# Method: use cloud-localds tool to create a seed ISO

# On Mac:
brew install cloud-utils  # if available, or use manual method

# Manual method - after flashing Ubuntu ISO to USB:
# The autoinstall files go in the root of the USB as:
# /user-data
# /meta-data
# Ubuntu installer looks for these automatically

# OR: Use a second small USB as the "seed" drive with just:
# user-data and meta-data files
```

**Simplest approach - use a seed USB:**
```bash
# Create a tiny FAT32 USB with just two files:
# user-data  (your autoinstall config)
# meta-data  (empty file)

# Ubuntu installer will find these on boot
```

### Boot each machine
1. Plug Ubuntu USB + seed USB into Optiplex
2. Power on, press **F12** for boot menu
3. Select Ubuntu USB
4. Install happens automatically (~10 min)
5. Machine reboots and SSH is ready

---

## Step 2: Prepare UniFi NFS Share

Ensure the NFS share on the UniFi drive (10.0.15.15) is exported and accessible:

```bash
# Verify NFS export is reachable from any node
showmount -e 10.0.15.15
```

The NFS path used is:
```
/volume/3ac9efb3-390c-47d2-a9f5-e0e04418172b/.srv/.unifi-drive/k3sstorage/.data
```

Ensure the export allows `10.0.20.0/24` with read/write access.

---

## Step 3: Run Ansible

```bash
# Install Ansible on Mac
brew install ansible

# Go to ansible directory
cd ansible/

# Test SSH connectivity to all nodes
ansible -i inventory/hosts.yml all -m ping

# Run full setup
ansible-playbook -i inventory/hosts.yml site.yml

# Run only specific steps if needed
ansible-playbook -i inventory/hosts.yml site.yml --tags common
ansible-playbook -i inventory/hosts.yml site.yml --limit heimdall
```

---

## Step 4: Configure kubectl on Mac

The kubeconfig is the cluster-admin credential. Never commit it (it's in `.gitignore`).

Ansible fetches it to `/tmp/k3s-kubeconfig`, but macOS clears `/tmp` on reboot, so copy it
right after the playbook runs. ⚠️ `cp` **overwrites** an existing `~/.kube/config`; if you
already have one, merge instead (or keep it as a separate file and set `KUBECONFIG`).

```bash
mkdir -p ~/.kube && chmod 700 ~/.kube
if [ -e ~/.kube/config ]; then echo "~/.kube/config exists; merge instead"
else cp /tmp/k3s-kubeconfig ~/.kube/config && chmod 600 ~/.kube/config; fi
```

Without Ansible (e.g. from a new machine), copy it straight from heimdall. k3s writes it
with mode 644, so no sudo is needed:

```bash
scp vaishak@10.0.20.160:/etc/rancher/k3s/k3s.yaml ~/.kube/config
sed -i '' 's#https://127.0.0.1:6443#https://10.0.20.160:6443#' ~/.kube/config   # macOS sed
chmod 600 ~/.kube/config
```

The API cert's SANs include `10.0.20.160` and `heimdall`, so either works as the server.

```bash

# Install kubectl and k9s
brew install kubectl k9s

# Verify
kubectl get nodes
# NAME       STATUS   ROLES                  AGE
# heimdall   Ready    control-plane,master   5m
# bestla     Ready    <none>                 3m
# mimir      Ready    <none>                 3m

# Launch k9s (terminal UI)
k9s
```

---

## Step 5: Verify NFS Storage

```bash
# Check StorageClass was created
kubectl get storageclass
# NAME         PROVISIONER      RECLAIMPOLICY   VOLUMEBINDINGMODE   ALLOWVOLUMEEXPANSION
# nfs-client   nfs.csi.k8s.io   Retain          Immediate           false

# Test with a PVC
kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: test-pvc
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: nfs-client
  resources:
    requests:
      storage: 1Gi
EOF

kubectl get pvc test-pvc
# Should show STATUS: Bound

# Clean up
kubectl delete pvc test-pvc
```

---

## Useful Commands

```bash
# Cluster status
kubectl get nodes -o wide
kubectl get pods --all-namespaces

# Node resource usage
kubectl top nodes

# Restart a deployment
kubectl rollout restart deployment/name -n namespace

# SSH into nodes
ssh vaishak@10.0.20.160  # heimdall
ssh vaishak@10.0.20.161  # bestla
ssh vaishak@10.0.20.162  # mimir

# K3s service logs
sudo journalctl -u k3s -f          # on heimdall
sudo journalctl -u k3s-agent -f    # on bestla/mimir

# Re-run Ansible after hardware changes
ansible-playbook -i inventory/hosts.yml site.yml
```

---

## Re-adding a Node

If a node fails and needs reinstalling:
```bash
# 1. Boot with autoinstall USB (Ubuntu installs automatically)
# 2. SSH available after reboot
# 3. Re-run Ansible (idempotent - safe to run again)
ansible-playbook -i inventory/hosts.yml site.yml --limit bestla
```

---

## Project Structure

```
k3s-setup/
├── README.md
├── autoinstall/
│   ├── heimdall/
│   │   ├── user-data    # Autoinstall config (fill in password + SSH key)
│   │   └── meta-data    # Empty file (required)
│   ├── bestla/
│   │   ├── user-data
│   │   └── meta-data
│   └── mimir/
│       ├── user-data
│       └── meta-data
└── ansible/
    ├── site.yml                      # Main playbook
    ├── inventory/
    │   └── hosts.yml                 # Node IPs and groups
    ├── group_vars/
    │   └── all.yml                   # Shared variables
    └── roles/
        ├── common/tasks/main.yml     # Runs on all nodes
        ├── k3s_server/tasks/main.yml # Heimdall only
        ├── k3s_agent/tasks/main.yml  # Bestla + Mimir
        └── nfs/tasks/main.yml        # NFS StorageClass setup
```
