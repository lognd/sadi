Event replay now accepts rotated multi-segment WALs: it tolerates a seq jump only over verified SEAL seqs reported by WalReader, and any other gap remains EventsGap.
