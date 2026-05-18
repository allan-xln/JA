import { Ionicons } from "@expo/vector-icons";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ImageBackground,
  LayoutChangeEvent,
  StyleProp,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
  ViewStyle,
} from "react-native";
import {
  Gesture,
  GestureDetector,
  GestureHandlerRootView,
} from "react-native-gesture-handler";
import Animated, {
  Easing,
  runOnJS,
  runOnUI,
  useAnimatedReaction,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
  type SharedValue,
} from "react-native-reanimated";

const MIN_SCALE = 1;
const MAX_SCALE = 5;
const DOUBLE_TAP_SCALE = 2.4;
const ZOOM_STEP = 0.25;
const TAP_MAX_DISTANCE = 8;
const GESTURE_COOLDOWN_MS = 180;
const PAN_MIN_DISTANCE = 5;
const HOTSPOT_DRAG_LONG_PRESS_MS = 180;

const HOTSPOT_CORE_SIZE = 18;
const HOTSPOT_PULSE_SIZE = 42;
const HOTSPOT_SELECTED_RING_SIZE = 56;

export type MapEditorCanvasHotspot = {
  id: string;
  name: string;
  x: number;
  y: number;
};

type MapEditorCanvasProps = {
  imageUrl?: string | null;
  title?: string | null;
  hotspots: MapEditorCanvasHotspot[];
  selectedHotspotId?: string | null;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
  onPressMap?: (params: { xPercent: number; yPercent: number }) => void;
  onSelectHotspot?: (hotspotId: string) => void;
  onMoveHotspot?: (params: {
    hotspotId: string;
    xPercent: number;
    yPercent: number;
  }) => void;
};

type HotspotMarkerProps = {
  hotspot: MapEditorCanvasHotspot;
  selected: boolean;
  disabled: boolean;
  scale: SharedValue<number>;
  layoutWidth: SharedValue<number>;
  layoutHeight: SharedValue<number>;
  pulseStyle: ReturnType<typeof useAnimatedStyle>;
  selectedPulseStyle: ReturnType<typeof useAnimatedStyle>;
  onSelectHotspot?: (hotspotId: string) => void;
  onMoveHotspot?: (params: {
    hotspotId: string;
    xPercent: number;
    yPercent: number;
  }) => void;
};

function clamp(value: number, min: number, max: number) {
  "worklet";
  return Math.max(min, Math.min(max, value));
}

function getPanLimits(
  width: number,
  height: number,
  nextScale: number,
): {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
} {
  "worklet";

  const extraWidth = Math.max(0, (width * nextScale - width) / 2);
  const extraHeight = Math.max(0, (height * nextScale - height) / 2);

  return {
    minX: -extraWidth,
    maxX: extraWidth,
    minY: -extraHeight,
    maxY: extraHeight,
  };
}

function clampTranslation(
  width: number,
  height: number,
  nextX: number,
  nextY: number,
  nextScale: number,
) {
  "worklet";

  const limits = getPanLimits(width, height, nextScale);

  return {
    x: clamp(nextX, limits.minX, limits.maxX),
    y: clamp(nextY, limits.minY, limits.maxY),
  };
}

function computeDoubleTapTranslate(params: {
  tapX: number;
  tapY: number;
  width: number;
  height: number;
  currentScale: number;
  nextScale: number;
  currentTranslateX: number;
  currentTranslateY: number;
}) {
  "worklet";

  const centerX = params.width / 2;
  const centerY = params.height / 2;

  const worldX =
    (params.tapX - centerX - params.currentTranslateX) / params.currentScale;
  const worldY =
    (params.tapY - centerY - params.currentTranslateY) / params.currentScale;

  const nextTranslateX = params.tapX - centerX - worldX * params.nextScale;
  const nextTranslateY = params.tapY - centerY - worldY * params.nextScale;

  return clampTranslation(
    params.width,
    params.height,
    nextTranslateX,
    nextTranslateY,
    params.nextScale,
  );
}

function applyTransformWorklet(params: {
  nextScale: number;
  width: number;
  height: number;
  translateX: SharedValue<number>;
  translateY: SharedValue<number>;
  scale: SharedValue<number>;
  savedScale: SharedValue<number>;
  startTranslateX: SharedValue<number>;
  startTranslateY: SharedValue<number>;
}) {
  "worklet";

  const safeScale = clamp(params.nextScale, MIN_SCALE, MAX_SCALE);

  const clamped = clampTranslation(
    params.width,
    params.height,
    params.translateX.value,
    params.translateY.value,
    safeScale,
  );

  params.scale.value = safeScale;
  params.savedScale.value = safeScale;
  params.translateX.value = clamped.x;
  params.translateY.value = clamped.y;
  params.startTranslateX.value = clamped.x;
  params.startTranslateY.value = clamped.y;
}

function HotspotMarker({
  hotspot,
  selected,
  disabled,
  scale,
  layoutWidth,
  layoutHeight,
  pulseStyle,
  selectedPulseStyle,
  onSelectHotspot,
  onMoveHotspot,
}: HotspotMarkerProps) {
  const xPercent = useSharedValue(hotspot.x);
  const yPercent = useSharedValue(hotspot.y);
  const startXPercent = useSharedValue(hotspot.x);
  const startYPercent = useSharedValue(hotspot.y);
  const isDragging = useSharedValue(false);

  useEffect(() => {
    xPercent.value = hotspot.x;
    yPercent.value = hotspot.y;
    startXPercent.value = hotspot.x;
    startYPercent.value = hotspot.y;
  }, [hotspot.x, hotspot.y, xPercent, yPercent, startXPercent, startYPercent]);

  const handlePress = useCallback(() => {
    if (disabled) return;
    onSelectHotspot?.(hotspot.id);
  }, [disabled, hotspot.id, onSelectHotspot]);

  const handleMoveCommit = useCallback(
    (nextX: number, nextY: number) => {
      onMoveHotspot?.({
        hotspotId: hotspot.id,
        xPercent: nextX,
        yPercent: nextY,
      });
    },
    [hotspot.id, onMoveHotspot],
  );

  const positionStyle = useAnimatedStyle(() => {
    return {
      left: `${xPercent.value}%`,
      top: `${yPercent.value}%`,
      opacity: isDragging.value ? 0.96 : 1,
    };
  });

  const dragGesture = Gesture.Pan()
    .enabled(!disabled && !!onMoveHotspot && selected)
    .activateAfterLongPress(HOTSPOT_DRAG_LONG_PRESS_MS)
    .minDistance(1)
    .onBegin(() => {
      isDragging.value = true;
      startXPercent.value = xPercent.value;
      startYPercent.value = yPercent.value;
      if (onSelectHotspot) {
        runOnJS(onSelectHotspot)(hotspot.id);
      }
    })
    .onUpdate((event) => {
      const width = layoutWidth.value;
      const height = layoutHeight.value;
      const currentScale = scale.value || 1;

      if (!width || !height) return;

      const nextX =
        ((startXPercent.value / 100) * width +
          event.translationX / currentScale) /
        width;

      const nextY =
        ((startYPercent.value / 100) * height +
          event.translationY / currentScale) /
        height;

      xPercent.value = clamp(nextX * 100, 0, 100);
      yPercent.value = clamp(nextY * 100, 0, 100);
    })
    .onEnd(() => {
      if (onMoveHotspot) {
        runOnJS(handleMoveCommit)(xPercent.value, yPercent.value);
      }
    })
    .onFinalize(() => {
      isDragging.value = false;
    });

  return (
    <GestureDetector gesture={dragGesture}>
      <Animated.View style={[styles.hotspot, positionStyle]}>
        <TouchableOpacity
          activeOpacity={0.9}
          onPress={handlePress}
          disabled={disabled}
          style={styles.hotspotTouch}
        >
          <Animated.View style={[styles.hotspotPulse, pulseStyle]} />

          {selected ? (
            <Animated.View
              style={[styles.hotspotSelectedRing, selectedPulseStyle]}
            />
          ) : null}

          <View
            style={[
              styles.hotspotCore,
              selected && styles.hotspotCoreSelected,
              isDragging.value ? styles.hotspotCoreDragging : null,
            ]}
          >
            <View style={styles.hotspotInnerDot} />
          </View>

          {selected ? (
            <View style={styles.hotspotLabel}>
              <Text style={styles.hotspotLabelText} numberOfLines={1}>
                {hotspot.name}
              </Text>
              <Text style={styles.hotspotLabelSubtext}>
                Segure e arraste para mover
              </Text>
            </View>
          ) : null}
        </TouchableOpacity>
      </Animated.View>
    </GestureDetector>
  );
}

export default function MapEditorCanvas({
  imageUrl,
  title,
  hotspots,
  selectedHotspotId,
  disabled = false,
  style,
  onPressMap,
  onSelectHotspot,
  onMoveHotspot,
}: MapEditorCanvasProps) {
  const [zoomLabel, setZoomLabel] = useState(100);

  const scale = useSharedValue(1);
  const savedScale = useSharedValue(1);

  const translateX = useSharedValue(0);
  const translateY = useSharedValue(0);
  const startTranslateX = useSharedValue(0);
  const startTranslateY = useSharedValue(0);

  const layoutWidth = useSharedValue(0);
  const layoutHeight = useSharedValue(0);

  const isPanning = useSharedValue(false);
  const isPinching = useSharedValue(false);
  const isGestureCoolingDown = useSharedValue(false);

  const pulse = useSharedValue(0);
  const selectedPulse = useSharedValue(0);

  const cooldownTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    pulse.value = withRepeat(
      withTiming(1, {
        duration: 1350,
        easing: Easing.inOut(Easing.ease),
      }),
      -1,
      false,
    );

    selectedPulse.value = withRepeat(
      withTiming(1, {
        duration: 1150,
        easing: Easing.inOut(Easing.ease),
      }),
      -1,
      true,
    );

    return () => {
      if (cooldownTimerRef.current) {
        clearTimeout(cooldownTimerRef.current);
      }
    };
  }, [pulse, selectedPulse]);

  const updateZoomLabel = useCallback((value: number) => {
    setZoomLabel(Math.round(value * 100));
  }, []);

  useAnimatedReaction(
    () => scale.value,
    (current, previous) => {
      if (current !== previous) {
        runOnJS(updateZoomLabel)(current);
      }
    },
    [updateZoomLabel],
  );

  const handleLayout = useCallback(
    (event: LayoutChangeEvent) => {
      const { width, height } = event.nativeEvent.layout;
      layoutWidth.value = width;
      layoutHeight.value = height;
    },
    [layoutHeight, layoutWidth],
  );

  const beginGestureCooldown = useCallback(() => {
    if (cooldownTimerRef.current) {
      clearTimeout(cooldownTimerRef.current);
    }

    isGestureCoolingDown.value = true;

    cooldownTimerRef.current = setTimeout(() => {
      isGestureCoolingDown.value = false;
    }, GESTURE_COOLDOWN_MS);
  }, [isGestureCoolingDown]);

  const resetView = useCallback(() => {
    runOnUI(() => {
      "worklet";
      scale.value = withTiming(1, { duration: 220 });
      savedScale.value = 1;
      translateX.value = withTiming(0, { duration: 220 });
      translateY.value = withTiming(0, { duration: 220 });
      startTranslateX.value = 0;
      startTranslateY.value = 0;
    })();
  }, [
    savedScale,
    scale,
    startTranslateX,
    startTranslateY,
    translateX,
    translateY,
  ]);

  const zoomIn = useCallback(() => {
    runOnUI(() => {
      "worklet";
      applyTransformWorklet({
        nextScale: scale.value + ZOOM_STEP,
        width: layoutWidth.value,
        height: layoutHeight.value,
        translateX,
        translateY,
        scale,
        savedScale,
        startTranslateX,
        startTranslateY,
      });
    })();
  }, [
    layoutHeight,
    layoutWidth,
    savedScale,
    scale,
    startTranslateX,
    startTranslateY,
    translateX,
    translateY,
  ]);

  const zoomOut = useCallback(() => {
    runOnUI(() => {
      "worklet";
      applyTransformWorklet({
        nextScale: scale.value - ZOOM_STEP,
        width: layoutWidth.value,
        height: layoutHeight.value,
        translateX,
        translateY,
        scale,
        savedScale,
        startTranslateX,
        startTranslateY,
      });
    })();
  }, [
    layoutHeight,
    layoutWidth,
    savedScale,
    scale,
    startTranslateX,
    startTranslateY,
    translateX,
    translateY,
  ]);

  const handleTapMap = useCallback(
    (
      x: number,
      y: number,
      width: number,
      height: number,
      currentScale: number,
      currentTranslateX: number,
      currentTranslateY: number,
    ) => {
      if (disabled || !onPressMap) return;
      if (!width || !height) return;

      if (currentScale > 1.08) {
        return;
      }

      const centerX = width / 2;
      const centerY = height / 2;

      const unscaledX =
        (x - centerX - currentTranslateX) / currentScale + centerX;
      const unscaledY =
        (y - centerY - currentTranslateY) / currentScale + centerY;

      const xPercent = Math.max(0, Math.min(100, (unscaledX / width) * 100));
      const yPercent = Math.max(0, Math.min(100, (unscaledY / height) * 100));

      onPressMap({ xPercent, yPercent });
    },
    [disabled, onPressMap],
  );

  const pulseStyle = useAnimatedStyle(() => {
    return {
      transform: [{ scale: 1 + pulse.value * 0.5 }],
      opacity: 0.22 - pulse.value * 0.14,
    };
  });

  const selectedPulseStyle = useAnimatedStyle(() => {
    return {
      transform: [{ scale: 1 + selectedPulse.value * 0.16 }],
      opacity: 0.2 + selectedPulse.value * 0.12,
    };
  });

  const panGesture = Gesture.Pan()
    .enabled(!disabled)
    .minDistance(PAN_MIN_DISTANCE)
    .onStart(() => {
      isPanning.value = false;
      startTranslateX.value = translateX.value;
      startTranslateY.value = translateY.value;
    })
    .onUpdate((event) => {
      if (
        Math.abs(event.translationX) > 6 ||
        Math.abs(event.translationY) > 6
      ) {
        isPanning.value = true;
      }

      const nextX = startTranslateX.value + event.translationX;
      const nextY = startTranslateY.value + event.translationY;

      const clamped = clampTranslation(
        layoutWidth.value,
        layoutHeight.value,
        nextX,
        nextY,
        scale.value,
      );

      translateX.value = clamped.x;
      translateY.value = clamped.y;
    })
    .onEnd(() => {
      startTranslateX.value = translateX.value;
      startTranslateY.value = translateY.value;
    })
    .onFinalize(() => {
      if (isPanning.value) {
        runOnJS(beginGestureCooldown)();
      }
      isPanning.value = false;
    });

  const pinchGesture = Gesture.Pinch()
    .enabled(!disabled)
    .onBegin(() => {
      isPinching.value = true;
    })
    .onUpdate((event) => {
      const nextScale = clamp(
        savedScale.value * event.scale,
        MIN_SCALE,
        MAX_SCALE,
      );

      const clamped = clampTranslation(
        layoutWidth.value,
        layoutHeight.value,
        translateX.value,
        translateY.value,
        nextScale,
      );

      scale.value = nextScale;
      translateX.value = clamped.x;
      translateY.value = clamped.y;
    })
    .onEnd(() => {
      savedScale.value = scale.value;
      startTranslateX.value = translateX.value;
      startTranslateY.value = translateY.value;
    })
    .onFinalize(() => {
      runOnJS(beginGestureCooldown)();
      isPinching.value = false;
    });

  const doubleTapGesture = Gesture.Tap()
    .enabled(!disabled)
    .numberOfTaps(2)
    .maxDuration(250)
    .onEnd((event, success) => {
      if (!success) return;

      runOnJS(beginGestureCooldown)();

      const nextScale =
        scale.value > 1.15
          ? MIN_SCALE
          : clamp(DOUBLE_TAP_SCALE, MIN_SCALE, MAX_SCALE);

      if (nextScale === MIN_SCALE) {
        scale.value = withTiming(1, { duration: 220 });
        savedScale.value = 1;
        translateX.value = withTiming(0, { duration: 220 });
        translateY.value = withTiming(0, { duration: 220 });
        startTranslateX.value = 0;
        startTranslateY.value = 0;
        return;
      }

      const nextTranslate = computeDoubleTapTranslate({
        tapX: event.x,
        tapY: event.y,
        width: layoutWidth.value,
        height: layoutHeight.value,
        currentScale: scale.value,
        nextScale,
        currentTranslateX: translateX.value,
        currentTranslateY: translateY.value,
      });

      scale.value = withTiming(nextScale, { duration: 220 });
      savedScale.value = nextScale;
      translateX.value = withTiming(nextTranslate.x, { duration: 220 });
      translateY.value = withTiming(nextTranslate.y, { duration: 220 });
      startTranslateX.value = nextTranslate.x;
      startTranslateY.value = nextTranslate.y;
    });

  const singleTapGesture = Gesture.Tap()
    .enabled(!disabled)
    .maxDuration(250)
    .maxDistance(TAP_MAX_DISTANCE)
    .onEnd((event, success) => {
      if (!success) return;
      if (isPanning.value || isPinching.value || isGestureCoolingDown.value) {
        return;
      }

      runOnJS(handleTapMap)(
        event.x,
        event.y,
        layoutWidth.value,
        layoutHeight.value,
        scale.value,
        translateX.value,
        translateY.value,
      );
    })
    .requireExternalGestureToFail(doubleTapGesture);

  const tapGesture = Gesture.Exclusive(doubleTapGesture, singleTapGesture);

  const composedGesture = Gesture.Simultaneous(
    panGesture,
    pinchGesture,
    tapGesture,
  );

  const animatedStyle = useAnimatedStyle(() => {
    return {
      transform: [
        { translateX: translateX.value },
        { translateY: translateY.value },
        { scale: scale.value },
      ],
    };
  });

  const hotspotItems = useMemo(() => {
    return hotspots.map((hotspot) => {
      const selected = hotspot.id === selectedHotspotId;

      return (
        <HotspotMarker
          key={hotspot.id}
          hotspot={hotspot}
          selected={selected}
          disabled={disabled}
          scale={scale}
          layoutWidth={layoutWidth}
          layoutHeight={layoutHeight}
          pulseStyle={pulseStyle}
          selectedPulseStyle={selectedPulseStyle}
          onSelectHotspot={onSelectHotspot}
          onMoveHotspot={onMoveHotspot}
        />
      );
    });
  }, [
    disabled,
    hotspots,
    layoutHeight,
    layoutWidth,
    onMoveHotspot,
    onSelectHotspot,
    pulseStyle,
    scale,
    selectedHotspotId,
    selectedPulseStyle,
  ]);

  return (
    <GestureHandlerRootView style={[styles.wrapper, style]}>
      <View style={styles.toolbar}>
        <View style={styles.zoomGroup}>
          <TouchableOpacity
            style={styles.toolButton}
            activeOpacity={0.9}
            onPress={zoomOut}
            disabled={disabled}
          >
            <Ionicons name="remove-outline" size={18} color="#FFFFFF" />
          </TouchableOpacity>

          <View style={styles.zoomLabelWrap}>
            <Text style={styles.zoomLabel}>{zoomLabel}%</Text>
          </View>

          <TouchableOpacity
            style={styles.toolButton}
            activeOpacity={0.9}
            onPress={zoomIn}
            disabled={disabled}
          >
            <Ionicons name="add-outline" size={18} color="#FFFFFF" />
          </TouchableOpacity>
        </View>

        <TouchableOpacity
          style={styles.resetViewButton}
          activeOpacity={0.9}
          onPress={resetView}
          disabled={disabled}
        >
          <Ionicons name="scan-outline" size={16} color="#FFFFFF" />
          <Text style={styles.resetViewButtonText}>Resetar visão</Text>
        </TouchableOpacity>
      </View>

      <GestureDetector gesture={composedGesture}>
        <View
          onLayout={handleLayout}
          style={[styles.canvas, disabled && styles.canvasDisabled]}
        >
          <View style={styles.viewport}>
            <Animated.View style={[styles.transformLayer, animatedStyle]}>
              {imageUrl ? (
                <ImageBackground
                  source={{ uri: imageUrl }}
                  resizeMode="contain"
                  style={styles.canvasInner}
                  imageStyle={styles.canvasImage}
                >
                  <View style={styles.overlay} />
                  {hotspotItems}
                </ImageBackground>
              ) : (
                <View style={styles.fallback}>
                  <View style={styles.fakeGrid} />
                  <Text style={styles.fallbackTitle}>
                    {title ?? "Sem imagem principal"}
                  </Text>
                  <Text style={styles.fallbackText}>
                    Você já pode criar hotspots mesmo sem a imagem. Quando subir
                    a planta, os pontos continuam salvos.
                  </Text>
                  {hotspotItems}
                </View>
              )}
            </Animated.View>
          </View>

          <View style={styles.hintWrap}>
            <Text style={styles.hint}>
              Arraste o mapa com 1 dedo • zoom com 2 dedos • duplo toque para
              zoom • toque curto para criar hotspot • segure o hotspot
              selecionado para mover
            </Text>
          </View>
        </View>
      </GestureDetector>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    width: "100%",
  },

  toolbar: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 10,
    marginBottom: 12,
    flexWrap: "wrap",
  },

  zoomGroup: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },

  toolButton: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: "rgba(255,255,255,0.06)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.10)",
    alignItems: "center",
    justifyContent: "center",
  },

  zoomLabelWrap: {
    minWidth: 66,
    height: 40,
    borderRadius: 12,
    backgroundColor: "rgba(255,255,255,0.05)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 10,
  },

  zoomLabel: {
    color: "#FFFFFF",
    fontSize: 12,
    fontWeight: "800",
  },

  resetViewButton: {
    minHeight: 40,
    paddingHorizontal: 12,
    borderRadius: 12,
    backgroundColor: "rgba(27, 92, 255, 0.16)",
    borderWidth: 1,
    borderColor: "rgba(27, 92, 255, 0.28)",
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },

  resetViewButtonText: {
    color: "#FFFFFF",
    fontSize: 12,
    fontWeight: "700",
  },

  canvas: {
    height: 360,
    borderRadius: 20,
    overflow: "hidden",
    backgroundColor: "rgba(255,255,255,0.04)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.06)",
    marginBottom: 14,
    position: "relative",
  },

  canvasDisabled: {
    opacity: 0.8,
  },

  viewport: {
    flex: 1,
    overflow: "hidden",
  },

  transformLayer: {
    width: "100%",
    height: "100%",
  },

  canvasInner: {
    width: "100%",
    height: "100%",
  },

  canvasImage: {
    borderRadius: 20,
  },

  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(4, 10, 20, 0.12)",
  },

  fallback: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    position: "relative",
    paddingHorizontal: 18,
    backgroundColor: "rgba(255,255,255,0.02)",
  },

  fakeGrid: {
    ...StyleSheet.absoluteFillObject,
    opacity: 0.12,
  },

  fallbackTitle: {
    color: "#FFFFFF",
    fontSize: 18,
    fontWeight: "800",
    marginBottom: 6,
    textAlign: "center",
  },

  fallbackText: {
    color: "rgba(255,255,255,0.72)",
    fontSize: 13,
    textAlign: "center",
    maxWidth: 280,
    lineHeight: 18,
    marginBottom: 10,
  },

  hintWrap: {
    position: "absolute",
    left: 12,
    right: 12,
    bottom: 12,
  },

  hint: {
    textAlign: "center",
    color: "#FFFFFF",
    fontSize: 11,
    fontWeight: "800",
    backgroundColor: "rgba(0,0,0,0.34)",
    paddingVertical: 9,
    paddingHorizontal: 12,
    borderRadius: 999,
  },

  hotspot: {
    position: "absolute",
    width: HOTSPOT_SELECTED_RING_SIZE,
    height: HOTSPOT_SELECTED_RING_SIZE,
    marginLeft: -(HOTSPOT_SELECTED_RING_SIZE / 2),
    marginTop: -(HOTSPOT_SELECTED_RING_SIZE / 2),
    alignItems: "center",
    justifyContent: "center",
  },

  hotspotTouch: {
    width: HOTSPOT_SELECTED_RING_SIZE,
    height: HOTSPOT_SELECTED_RING_SIZE,
    alignItems: "center",
    justifyContent: "center",
  },

  hotspotPulse: {
    position: "absolute",
    width: HOTSPOT_PULSE_SIZE,
    height: HOTSPOT_PULSE_SIZE,
    borderRadius: 999,
    backgroundColor: "rgba(46,204,113,0.28)",
  },

  hotspotSelectedRing: {
    position: "absolute",
    width: HOTSPOT_SELECTED_RING_SIZE,
    height: HOTSPOT_SELECTED_RING_SIZE,
    borderRadius: 999,
    backgroundColor: "rgba(46,204,113,0.18)",
  },

  hotspotCore: {
    width: HOTSPOT_CORE_SIZE,
    height: HOTSPOT_CORE_SIZE,
    borderRadius: 999,
    backgroundColor: "#2ecc71",
    borderWidth: 3,
    borderColor: "#FFFFFF",
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#2ecc71",
    shadowOpacity: 0.28,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 0 },
    elevation: 8,
  },

  hotspotCoreSelected: {
    transform: [{ scale: 1.18 }],
    shadowOpacity: 0.48,
    shadowRadius: 14,
    elevation: 12,
  },

  hotspotCoreDragging: {
    transform: [{ scale: 1.24 }],
    shadowOpacity: 0.6,
    shadowRadius: 16,
    elevation: 14,
  },

  hotspotInnerDot: {
    width: 6,
    height: 6,
    borderRadius: 999,
    backgroundColor: "#04110B",
  },

  hotspotLabel: {
    position: "absolute",
    top: HOTSPOT_SELECTED_RING_SIZE - 2,
    minWidth: 92,
    maxWidth: 160,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 10,
    backgroundColor: "rgba(6, 12, 24, 0.88)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
  },

  hotspotLabelText: {
    color: "#FFFFFF",
    fontSize: 11,
    fontWeight: "800",
    textAlign: "center",
  },

  hotspotLabelSubtext: {
    marginTop: 2,
    color: "rgba(255,255,255,0.72)",
    fontSize: 10,
    fontWeight: "700",
    textAlign: "center",
  },
});
