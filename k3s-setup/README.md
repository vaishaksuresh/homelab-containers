# K3s Cluster Setup

## Nodes
| Hostname | IP | Role |
|----------|-----|------|
| heimdall | 10.0.20.160 | K3s server (control plane) |
| bestla | 10.0.20.161 | K3s agent (worker) |
| mimir | 10.0.20.162 | K3s agent (worker) |

**NFS Storage:** QNAP NAS at 10.0.20.196

---

## Step 1: Prepare Autoinstall USBs

### Generate password hash (on your Mac)
```bash
python3 -c "import crypt; print(crypt.crypt('yourpassword', crypt.mksalt(crypt.METHOD_SHA512)))"
```

### Get your SSH public key
```bash
cat ~/.ssh/id_rsa.pub
# If you don't have one: ssh-keygen -t rsa -b 4096
```

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

## Step 2: Prepare QNAP NFS Share

```bash
# SSH into NAS
ssh admin@10.0.20.196 -p 1022

# Create storage directory
mkdir -p /share/CACHEDEV1_DATA/k3s-storage

# Enable NFS in QNAP UI:
# Control Panel > Network & File Services > NFS Service > Enable NFS
# Set quota on folder if desired (Control Panel > Privilege > Shared Folders)
```

**Add NFS export in QNAP UI:**
1. File Station → right-click `k3s-storage` → Properties → NFS Host Access
2. Add rule:
   - Hostname/IP: `10.0.20.0/24`
   - Access right: Read/Write
   - Squash: No squash
   - Security: sys

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

```bash
# Ansible fetches kubeconfig to /tmp/k3s-kubeconfig
# Copy to your .kube directory
cp /tmp/k3s-kubeconfig ~/.kube/config

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
