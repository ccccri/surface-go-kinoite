#!/bin/bash
# Runs every test of Surface Control on the tablet. The camera and audio ones touch the real hardware and put your settings back.
cd "$(dirname "$0")/.." || exit 1
fail=0
for t in test_pages test_backend test_valuefield test_nfc_window test_keyboard test_eq_ui test_pen test_eq stress_audio stress_preview fuzz_profile; do
    printf '%-18s ' "$t"
    out=$(timeout 300 python3 -u tests/$t.py 2>&1); rc=$?
    echo "$out" | tail -1
    [ $rc = 0 ] || { fail=1; echo "$out" | grep -i "FAIL\|Traceback\|Error" | head -5; }
done
printf '%-18s ' wizard; QT_QPA_PLATFORM=offscreen python3 -u ../installer/tests/test_wizard.py 2>&1 | tail -1
printf '%-18s ' wizard-start; QT_QPA_PLATFORM=offscreen timeout 5 python3 ../installer/installer.py >/tmp/wiz_start.log 2>&1; [ $? = 124 ] && echo "opens and stays up" || { echo "FAIL the installer window did not start"; head -3 /tmp/wiz_start.log; fail=1; }
# every page opened in the real window for a few seconds: no warnings, no crash
for pg in overview updates cameras input audio nfc stylus sensors; do
    python3 main.py --page $pg >/tmp/page_$pg.log 2>&1 & p=$!
    sleep 5
    if kill -0 $p 2>/dev/null; then kill $p; wait $p 2>/dev/null; else echo "page $pg: the app died"; fail=1; fi
    grep -qi "warn\|error\|undefined\|typeerror\|binding loop" /tmp/page_$pg.log && { echo "page $pg printed:"; head -3 /tmp/page_$pg.log; fail=1; }
done
[ $fail = 0 ] && echo "ALL TESTS PASSED" || echo "SOME TESTS FAILED"
exit $fail
