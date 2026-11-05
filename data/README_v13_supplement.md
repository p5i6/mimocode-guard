# v1.3 supplement data

File: `v13_supplement_train.jsonl`

This is a curated 46-row Bash supplement for the MiMoCode Guard 1.3 Train split. It emphasizes:
- Safe/read-only device and firmware inspection (`lsblk`, `blkid`, `blockdev --get*`, `smartctl`, `flashrom` read/verify/probe).
- Scoped cleanup and permission changes.
- Destructive disk, partition, filesystem, firmware, and broad-permission operations.
- Remote shell execution and Git data-loss cases.

Risk labels use the upstream five-level taxonomy: safe, low, moderate, high, critical. Every row includes explanation, safer alternative, provenance identifier, and a family ID. The records use placeholders such as `/dev/sdX`; they are data and have not been executed.

## Source references

- util-linux: https://man7.org/linux/man-pages/man8/lsblk.8.html ; https://man7.org/linux/man-pages/man8/blkid.8.html ; https://man7.org/linux/man-pages/man8/blockdev.8.html ; https://man7.org/linux/man-pages/man8/wipefs.8.html
- smartmontools: https://manpages.debian.org/smartmontools/smartctl.8.en.html
- flashrom: https://manpages.debian.org/testing/flashrom/flashrom.8.en.html
- GNU Coreutils: https://www.gnu.org/software/coreutils/manual/
- GNU findutils: https://www.gnu.org/software/findutils/manual/html_mono/find.html
- GNU Parted: https://www.gnu.org/software/parted/manual/parted.html
- e2fsprogs: https://man7.org/linux/man-pages/man8/mke2fs.8.html
- iproute2: https://man7.org/linux/man-pages/man8/ip-link.8.html
- Git: https://git-scm.com/docs/git-reset ; https://git-scm.com/docs/git-clean

The source identifiers in each row map to the corresponding manual/project above. This is a curator-prepared batch, not a claim of independent expert annotation. It must pass the repository validator and upstream split-overlap checks before merging into a training dataset.
