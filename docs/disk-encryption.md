# Encrypting this workstation in place

Converts the existing root filesystem to LUKS2 **without reinstalling**, then
binds it to the TPM so it unlocks unattended, then blanks the login keyring
password.

Written for this machine specifically. Every device node and UUID below is real
— check them against `lsblk` before you type anything.

## This machine

| | |
|---|---|
| target | `/dev/nvme0n1p7` — btrfs, subvols `root` + `home`, UUID `14cdffcc-9137-42c4-9a40-89162f9d1847` |
| size | 211G, ~81G used, ~129G free |
| `/boot` | `/dev/nvme0n1p6`, ext4, **stays unencrypted** |
| `/boot/efi` | `/dev/nvme0n1p1`, vfat |
| Windows | `/dev/nvme0n1p3` — **untouched** |
| swap | zram only, no disk swap → no `resume=` to fix |
| Secure Boot | enabled → PCR 7 is meaningful |

Two things that make this easier than the general case: `/boot` is a separate
unencrypted partition, so GRUB never has to read LUKS; and there is no disk swap,
so there is no hibernation image to relocate.

## Before you start

**Back up first. This rewrites all 211G in place.** An interrupted reencrypt is
recoverable only from the LUKS2 header backup, and a mistake is not recoverable
at all. `~/Documents`, `~/code`, `~/recovered` and `~/incidents` are ~43G of data
recovered from the WSL image and the Windows partition — if that is not copied to
an external disk, stop here.

```bash
# external disk mounted at /run/media/tyler/BACKUP
rsync -aHAX --info=progress2 \
  /home/tyler/{Documents,Pictures,Videos,code,recovered,incidents} \
  /run/media/tyler/BACKUP/pre-luks/
```

Also: have the Fedora live USB written and **tested** before you begin, and be on
mains power.

## 1. Make room for the LUKS header (from the running system)

LUKS2 needs ~16M at the start of the device; `--reduce-device-size 32M` gives
headroom. btrfs can shrink online.

```bash
sudo btrfs filesystem resize -64M /
sudo btrfs filesystem show /            # confirm it shrank
sync
```

## 2. Reencrypt (from the live USB)

Boot the Fedora live USB. **Do not mount `/dev/nvme0n1p7`.**

```bash
sudo cryptsetup luksHeaderBackup /dev/nvme0n1p7 \
     --header-backup-file /run/media/.../luks-header.img 2>/dev/null || true

sudo cryptsetup reencrypt --encrypt --reduce-device-size 32M \
     --type luks2 /dev/nvme0n1p7
```

It asks for a passphrase — this is your recovery passphrase. **Write it down
before you continue.** If the TPM binding ever breaks this is the only way in.

Expect roughly 40–90 minutes for 211G on NVMe. It is resumable:
`cryptsetup reencrypt --resume-only /dev/nvme0n1p7`.

## 3. Reconnect the system

Still on the live USB:

```bash
sudo cryptsetup open /dev/nvme0n1p7 luks-root
sudo mount -o subvol=root /dev/mapper/luks-root /mnt
sudo mount -o subvol=home /dev/mapper/luks-root /mnt/home
sudo mount /dev/nvme0n1p6 /mnt/boot
sudo mount /dev/nvme0n1p1 /mnt/boot/efi
for d in dev proc sys run; do sudo mount --bind /$d /mnt/$d; done
sudo chroot /mnt /bin/bash
```

Inside the chroot — capture the **new** LUKS UUID (it is not the old btrfs UUID):

```bash
LUKS_UUID=$(blkid -s UUID -o value /dev/nvme0n1p7)
echo "LUKS UUID: $LUKS_UUID"

echo "luks-root UUID=$LUKS_UUID none discard" >> /etc/crypttab

# point the kernel at the mapper device, not the raw partition
sed -i "s|rd.luks.uuid=[^ \"]*||g" /etc/default/grub
sed -i "s|^GRUB_CMDLINE_LINUX=\"|GRUB_CMDLINE_LINUX=\"rd.luks.uuid=$LUKS_UUID |" /etc/default/grub
grep GRUB_CMDLINE_LINUX /etc/default/grub

# /etc/fstab keeps the SAME btrfs UUID — the filesystem inside LUKS is unchanged
```

Rebuild the initramfs and GRUB config:

```bash
dracut --force --regenerate-all
grub2-mkconfig -o /boot/grub2/grub.cfg
[ -d /sys/firmware/efi ] && grub2-mkconfig -o /boot/efi/EFI/fedora/grub.cfg
exit
```

Unmount and reboot:

```bash
for d in run sys proc dev; do sudo umount /mnt/$d; done
sudo umount /mnt/boot/efi /mnt/boot /mnt/home /mnt
sudo cryptsetup close luks-root
sudo reboot
```

You should be prompted for the passphrase at boot. **Confirm that works before
going near the TPM.**

## 4. Bind to the TPM

Back on the installed system:

```bash
cd ~/code/tyler/ansible-workstation
ansible-playbook playbook.yml --ask-become-pass --tags luks
```

That runs `roles/luks_tpm`, which enrols `--tpm2-pcrs=7` and switches
`/etc/crypttab` to `tpm2-device=auto`. To do it by hand instead:

```bash
sudo systemd-cryptenroll --wipe-slot=tpm2 /dev/nvme0n1p7
sudo systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=7 /dev/nvme0n1p7
sudo dracut --force
```

**Why PCR 7 alone.** PCR 0 measures the firmware, so a BIOS update changes it and
the TPM stops releasing the key. PCR 7 measures Secure Boot policy, which
survives firmware updates. The `gotylergo` playbook used `0+7`; that is the
version that breaks on BIOS updates.

**Keep the passphrase slot.** Never `--wipe-slot=password`. The TPM slot is a
convenience; the passphrase is how you get in when it fails.

**NVIDIA/MOK caveat.** Secure Boot is on and `akmod-nvidia` is signed with an
enrolled MOK. Depending on shim version, re-enrolling a MOK can alter PCR 7 and
invalidate the binding. If a driver update ever leaves you at a passphrase
prompt, that is why — re-run the enrol command above.

## 5. Blank the login keyring password

Only now, with the disk encrypted, does this become reasonable: a blank keyring
password stores secrets unencrypted, which is only acceptable because the volume
underneath is encrypted at rest.

```bash
seahorse &
```

Passwords → right-click **Login** → *Change Password* → enter your current
password, leave the new one empty → confirm the warning.

Chrome, Slack and anything else using the Secret Service will stop prompting.

## What this does not fix

Face unlock (Howdy) and fingerprint authenticate without ever producing your
password, so neither can unlock a *non-blank* keyring. That is why the keyring is
blanked rather than tied to biometrics — it is the only combination that gives
unattended unlock and encryption at rest together.

## If it goes wrong

| symptom | fix |
|---|---|
| reencrypt interrupted | `cryptsetup reencrypt --resume-only /dev/nvme0n1p7` from live USB |
| boots to `dracut` emergency shell | `rd.luks.uuid` wrong or missing — check `/etc/default/grub`, redo step 3 |
| passphrase prompt after a BIOS/MOK change | expected; unlock with the passphrase, re-run the TPM enrol |
| LUKS header damaged | `cryptsetup luksHeaderRestore /dev/nvme0n1p7 --header-backup-file …` |
| everything is broken | reinstall from the live USB and re-run this playbook; restore `~` from the backup |
