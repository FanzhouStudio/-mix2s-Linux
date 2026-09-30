/*
 * UPower 1.91.1 changes Charging to Discharging whenever current_now < 0.
 * The Polaris qcom_fg fuel gauge reports a negative current while its
 * status is Charging. Restrict this compatibility quirk to that one supply.
 *
 * Loaded only into upowerd through a systemd service drop-in. It leaves
 * current_now in sysfs and all other processes untouched.
 */

typedef struct _GUdevDevice GUdevDevice;

extern void *dlsym(void *handle, const char *symbol);
extern int strcmp(const char *a, const char *b);
extern char *strstr(const char *haystack, const char *needle);
extern const char *g_udev_device_get_sysfs_path(GUdevDevice *device);
extern const char *g_udev_device_get_sysfs_attr_uncached(GUdevDevice *device,
                                                         const char *attribute);

typedef double (*read_double_fn)(GUdevDevice *, const char *);

double
g_udev_device_get_sysfs_attr_as_double_uncached(GUdevDevice *device,
                                                 const char *attribute)
{
    static read_double_fn original;
    double value;
    const char *path;
    const char *status;

    if (!original)
        original = (read_double_fn)dlsym((void *)-1L,
            "g_udev_device_get_sysfs_attr_as_double_uncached");
    if (!original)
        return 0.0;

    value = original(device, attribute);
    if (value >= 0.0 || strcmp(attribute, "current_now") != 0)
        return value;

    path = g_udev_device_get_sysfs_path(device);
    if (!path || !strstr(path, "/power_supply/qcom-battery"))
        return value;

    status = g_udev_device_get_sysfs_attr_uncached(device, "status");
    if (!status || strcmp(status, "Charging") != 0)
        return value;

    return -value;
}
