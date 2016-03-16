# ------------------ Baseline tests -----------------
# python test.py -fmarch_tests -cbaseline -s1 -v0 -P2,6 -t40.0,40.0 -u1,1,0 \
# -C100.0m -mno_markers -q-1 -Sstandalone
# ------------------ UGUALE tests ------------------

# repeat failed tests
python test.py -fmarch_tests -cuguale_repeat -s1 -p2,7 -t40.0,40.0 -u3,3,3 -C100.0m \
-miptables_markers -q-1 -Suguale -Q14 -k1 -w20m

python test.py -fmarch_tests -cuguale_repeat -s1 -p2,7 -t40.0,40.0 -u3,3,3 -C100.0m \
-miptables_markers -q-1 -Suguale -Q8,10,12,14 -k1 -w10m

# even smaller bands
python test.py -fmarch_tests -cuguale -s1 -P2,2 -t40.0,40.0 -u1,1,0 -C100.0m \
-miptables_markers,buckets_markers -q-1 -Suguale -Q8,10,12,14 -k1 -w5m

python test.py -fmarch_tests -cuguale -s1 -P2,6 -t40.0,40.0 -u1,1,0 -C100.0m \
-miptables_markers,buckets_markers -q-1 -Suguale -Q8,10,12,14 -k1 -w5m

python test.py -fmarch_tests -cuguale -s1 -P2,4,6 -t40.0,40.0 -u1,1,1 -C100.0m \
-miptables_markers,buckets_markers -q-1 -Suguale -Q8,10,12,14 -k1 -w5m

python test.py -fmarch_tests -cuguale -s1 -p2,7 -t40.0,40.0 -u2,2,2 -C100.0m \
-miptables_markers,buckets_markers -q-1 -Suguale -Q8,10,12,14 -k1 -w5m

python test.py -fmarch_tests -cuguale -s1 -p2,7 -t40.0,40.0 -u3,3,3 -C100.0m \
-miptables_markers,buckets_markers -q-1 -Suguale -Q8,10,12,14 -k1 -w5m