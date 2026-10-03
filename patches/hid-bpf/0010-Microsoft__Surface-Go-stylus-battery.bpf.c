// SPDX-License-Identifier: GPL-2.0-only
/*
 * Surface Go (ELAN9038 digitizer, i2c 04F3:261A): the report descriptor declares a Digitizer "Battery Strength"
 * usage (0x3b) that never carries data, so the kernel creates a power_supply that always says "0%/1%, discharging".
 * The real pen battery comes over Bluetooth. Turn the usage into "Undefined" (0x00) so no fake battery is created.
 */
#include "vmlinux.h"
#include "hid_bpf.h"
#include "hid_bpf_helpers.h"
#include <bpf/bpf_tracing.h>

#define VID_ELAN	0x04F3
#define PID_SURFACE_GO	0x261A
#define RDESC_SIZE	948
#define BATT_OFFSET	644	/* 09 3b 25 64 81 42: Usage(Battery Strength), Logical Max(100), Input */

HID_BPF_CONFIG(
	HID_DEVICE(BUS_I2C, HID_GROUP_ANY, VID_ELAN, PID_SURFACE_GO)
);

SEC(HID_BPF_RDESC_FIXUP)
int BPF_PROG(hid_rdesc_fixup_surface_go_stylus_battery, struct hid_bpf_ctx *hctx)
{
	__u8 *data = hid_bpf_get_data(hctx, 0, HID_MAX_DESCRIPTOR_SIZE);

	if (!data)
		return 0; /* EPERM check */

	if (data[BATT_OFFSET] == 0x09 && data[BATT_OFFSET + 1] == 0x3b)
		data[BATT_OFFSET + 1] = 0x00;

	return 0;
}

HID_BPF_OPS(surface_go_stylus_battery) = {
	.hid_rdesc_fixup = (void *)hid_rdesc_fixup_surface_go_stylus_battery,
};

SEC("syscall")
int probe(struct hid_bpf_probe_args *ctx)
{
	ctx->retval = ctx->rdesc_size != RDESC_SIZE;
	if (ctx->retval)
		ctx->retval = -EINVAL;

	return 0;
}

char _license[] SEC("license") = "GPL";
