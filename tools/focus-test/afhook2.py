import sys
d = sys.argv[1]
s = open(d + "/af.cpp").read()
old = "	currentVariance_ = afEstimateVariance(y_items, true);\n"
assert old in s
s = s.replace(old, old + """
	/* TEST HOOK (never install): freeze the lens at the step in /dev/shm/afpos and log the AF variance there. */
	if (FILE *hf = fopen("/dev/shm/afpos", "r")) {
		int hp = -1;
		if (fscanf(hf, "%d", &hp) == 1 && hp >= 0) {
			context.activeState.af.focus = hp;
			context.activeState.af.stable = true;
			LOG(IPU3Af, Info) << "HOOK " << hp << " " << currentVariance_;
			fclose(hf);
			return;
		}
		fclose(hf);
	}
""", 1)
if "#include <cstdio>" not in s:
    s = s.replace("#include <cmath>", "#include <cmath>\n#include <cstdio>", 1)
open(d + "/af.cpp", "w").write(s)
