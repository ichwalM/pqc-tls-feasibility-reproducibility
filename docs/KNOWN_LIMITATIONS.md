# Known limitations

The repository must be interpreted together with the following limitations:

1. The classical and hybrid Nginx endpoints returned different response-body
   strings. The effect of this payload difference cannot be isolated from the
   end-to-end workload measurements.
2. Classical measurements preceded hybrid measurements on each server. Session
   drift and configuration order are therefore confounded.
3. The three servers differ simultaneously in processor, memory, storage, and
   platform characteristics. Cross-server differences cannot be attributed to
   hardware generation alone.
4. The dedicated connection-establishment metric includes client and
   instrumentation overhead and is not an isolated cryptographic-operation
   timing.
5. End-to-end request latency does not separately report TCP, TLS, and HTTP
   stages.
6. Network conditions were configured through `tc/netem`; the archived dataset
   does not contain an independent packet-level validation for every run.
7. CPU and resident-memory values are monitored-process summaries. They should
   not be interpreted as direct ML-KEM operation measurements.
8. Authentication remained classical. The experiment does not represent a
   fully post-quantum TLS deployment.

