# Configuration archive

`nginx-classical.conf` and `nginx-hybrid.conf` are copies of the archived
configuration files associated with the experiment. They are evidence of the
deployed comparison, not corrected payload-matched replacements.

The two files intentionally preserve the discovered response-body difference:

- classical: `classical-ok\n`
- hybrid: `hybrid-ok\n`

Do not edit these archived files if the goal is to document the reported
experiment. For a future rerun, create separate payload-matched configurations
and randomize or interleave execution order.

`tiers.example.yaml` is a redacted example. Its addresses belong to the
documentation-only `192.0.2.0/24` range and will not reach the original systems.
Copy it to `tiers.yaml` and provide local values only when running a new
experiment. Never commit private credentials or SSH keys.

