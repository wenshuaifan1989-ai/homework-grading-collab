import { onBeforeUnmount, onMounted, readonly, ref, type Ref } from 'vue';

export interface StudentDeviceHints {
    userAgent?: string;
    platform?: string;
    maxTouchPoints?: number;
    mobile?: boolean;
    coarsePointer?: boolean;
}

// This is a presentation hint. Student permissions always come from the server.
export function isStudentHandheldDevice(hints: StudentDeviceHints = {}): boolean {
    return hints.mobile === true
        || /Android|iPhone|iPad|iPod|Windows Phone|Mobile|Silk|Kindle/i.test(hints.userAgent || '')
        || (hints.platform === 'MacIntel' && (hints.maxTouchPoints || 0) > 1)
        || (hints.coarsePointer === true && (hints.maxTouchPoints || 0) > 0);
}

export function useStudentHandheld(): Readonly<Ref<boolean>> {
    let pointer: MediaQueryList | undefined;
    function detect() {
        if (typeof navigator === 'undefined') return false;
        const deviceNavigator = navigator as Navigator & { userAgentData?: { mobile?: boolean } };
        return isStudentHandheldDevice({
            userAgent: deviceNavigator.userAgent,
            platform: deviceNavigator.platform,
            maxTouchPoints: deviceNavigator.maxTouchPoints,
            mobile: deviceNavigator.userAgentData?.mobile,
            coarsePointer: pointer?.matches ?? (typeof window !== 'undefined'
                && typeof window.matchMedia === 'function' && window.matchMedia('(pointer: coarse)').matches),
        });
    }
    const handheld = ref(detect());
    const update = () => { handheld.value = detect(); };
    onMounted(() => {
        if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
        pointer = window.matchMedia('(pointer: coarse)');
        update();
        if (typeof pointer.addEventListener === 'function') pointer.addEventListener('change', update);
        else pointer.addListener?.(update);
    });
    onBeforeUnmount(() => {
        if (typeof pointer?.removeEventListener === 'function') pointer.removeEventListener('change', update);
        else pointer?.removeListener?.(update);
        pointer = undefined;
    });
    return readonly(handheld);
}
