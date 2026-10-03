p = "src/ipa/ipu3/algorithms/af.cpp"
s = open(p).read()
assert "TEST HOOK" not in s
s = s.replace("#include <cmath>\n", "#include <cmath>\n#include <cstdio>\n#include <cstdlib>\n", 1)
hook = '''	currentVariance_ = afEstimateVariance(y_items, true);

	/* TEST HOOK: /dev/shm/afpos holds a fixed VCM position; while it exists the autofocus is frozen there. */
	if (FILE *f = fopen("/dev/shm/afpos", "r")) {
		int pos = -1;
		if (fscanf(f, "%d", &pos) == 1 && pos >= 0 && pos <= 1023) {
			context.activeState.af.focus = pos;
			context.activeState.af.stable = true;
			LOG(IPU3Af, Debug) << "HOOK focus " << pos << " variance " << currentVariance_;
			fclose(f);
			return;
		}
		fclose(f);
	}
	LOG(IPU3Af, Debug) << "AFVAR step " << context.activeState.af.focus << " variance " << currentVariance_;
'''
old = "	currentVariance_ = afEstimateVariance(y_items, true);\n"
assert old in s
s = s.replace(old, hook, 1)
open(p, "w").write(s)
print("patched")
