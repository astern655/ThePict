// 카메라 실시간 프레임 획득 스파이크 (임시 · 검증용).
//
// 목적: Flutter **웹**에서 카메라 프레임을 얻어 프리뷰 + 오버레이가 실제로 그려지는지
// 증명한다. `camera` 패키지의 startImageStream은 웹 미지원이라, 웹에서 되는 유일 경로인
// getUserMedia + <video>(프리뷰) + <canvas>(캡처)를 쓴다. 서버 연동은 이 스코프 밖이다.
//
// 이 파일은 스파이크다. 프로덕션 통합(workout 화면)은 다음 단계. 커밋하지 않는다.

// 웹 전용 파일이다(getUserMedia/<video>/<canvas>). Flutter의 크로스플랫폼 경고 린트를
// 이 파일에 한해 끈다 — 의도된 웹 전용 경로다.
// ignore_for_file: avoid_web_libraries_in_flutter

import 'dart:async';
import 'dart:convert';
import 'dart:js_interop';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui_web' as ui_web;

import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

/// 프레임 소스 추상 경계 — 나중에 모바일(`MobileFrameSource`, camera 패키지 이미지 스트림)을
/// 같은 인터페이스로 끼울 수 있게 둔다. 이번 스파이크는 웹 구현(`WebFrameSource`)만 있다.
///
/// 프리뷰(`preview`)와 프레임 바이트(`frames`)를 분리해서 노출하는 이유:
///  - 웹: 프리뷰는 <video>(HtmlElementView), 프레임은 <canvas> 캡처 → 별개 경로.
///  - 모바일: 프리뷰는 CameraPreview, 프레임은 startImageStream → 역시 별개 경로.
/// 두 플랫폼 다 "화면에 보이는 것"과 "서버로 보낼 바이트"의 출처가 달라서 이 분리가 자연스럽다.
abstract class FrameSource {
  /// 다운스케일된 JPEG 프레임 바이트 스트림. 시작 후에만 흐른다.
  Stream<Uint8List> frames();

  /// 프리뷰 위젯. 카메라가 열린 뒤에만 유효하다(`start` 완료 후 호출).
  Widget preview();

  /// 카메라/타이머/스트림을 모두 정리한다. 멱등.
  void stop();
}

/// 웹 프레임 소스: getUserMedia로 카메라를 열고, <video>를 HtmlElementView로 노출하며,
/// 주기적으로 <video>를 오프스크린 <canvas>에 그려 JPEG로 뽑아 스트림에 흘린다.
class WebFrameSource implements FrameSource {
  WebFrameSource({this.targetWidth = 480, this.fps = 8});

  /// 캡처(다운스케일) 프레임의 가로 픽셀. 세로는 카메라 종횡비로 자동 계산.
  final int targetWidth;

  /// 초당 캡처 프레임 수.
  final int fps;

  final _controller = StreamController<Uint8List>.broadcast();

  // HtmlElementView 등록용 고유 viewType. 인스턴스마다 유일하게 만들어 핫리스타트 시
  // "이미 등록됨" 충돌을 피한다.
  final String _viewType =
      'camera-spike-video-${DateTime.now().microsecondsSinceEpoch}';

  web.MediaStream? _stream;
  web.HTMLVideoElement? _video;
  final web.HTMLCanvasElement _canvas = web.HTMLCanvasElement();
  Timer? _timer;
  bool _registered = false;

  @override
  Stream<Uint8List> frames() => _controller.stream;

  /// 카메라를 연다. 실패(권한 거부/미지원/비보안 컨텍스트)하면 예외를 던진다 — 호출자가 잡아
  /// "카메라를 쓸 수 없어요"를 표시한다.
  Future<void> start() async {
    final constraints = web.MediaStreamConstraints(
      video: web.MediaTrackConstraints(facingMode: 'user'.toJS),
      audio: false.toJS,
    );
    // 비보안 오리진이면 mediaDevices 자체가 없어 여기서 던진다.
    final stream =
        await web.window.navigator.mediaDevices.getUserMedia(constraints).toDart;
    _stream = stream;

    final video = web.HTMLVideoElement()
      ..autoplay = true
      ..muted = true
      ..srcObject = stream;
    video.setAttribute('playsinline', 'true');
    video.style
      ..width = '100%'
      ..height = '100%'
      ..objectFit = 'cover';
    _video = video;
    // muted autoplay는 브라우저 정책상 허용된다. play() 프라미스는 무시해도 안전.
    video.play();

    if (!_registered) {
      ui_web.platformViewRegistry
          .registerViewFactory(_viewType, (int _) => video);
      _registered = true;
    }

    final periodMs = (1000 / fps).round();
    _timer = Timer.periodic(Duration(milliseconds: periodMs), (_) => _capture());
  }

  void _capture() {
    final video = _video;
    if (video == null) return;
    final vw = video.videoWidth;
    final vh = video.videoHeight;
    // 아직 첫 프레임이 준비되기 전이면 종횡비를 모른다 — 건너뛴다.
    if (vw == 0 || vh == 0) return;

    final w = targetWidth;
    final h = (targetWidth * vh / vw).round();
    if (_canvas.width != w) _canvas.width = w;
    if (_canvas.height != h) _canvas.height = h;

    final ctx = _canvas.getContext('2d') as web.CanvasRenderingContext2D;
    // package:web는 drawImage 오버로드를 하나로 합쳤다. (image, dx, dy, dw, dh) 형태로
    // 전체 영상을 w×h로 스케일해 그린다.
    ctx.drawImage(video, 0, 0, w, h);

    // toDataURL은 동기·콜백 없음이라 스파이크에 가장 단순하다. data URL의 base64 부분만
    // 잘라 디코드하면 정확한 JPEG 바이트가 나온다(전송 크기 측정에 그대로 쓸 수 있음).
    final dataUrl = _canvas.toDataURL('image/jpeg', 0.6.toJS);
    final comma = dataUrl.indexOf(',');
    if (comma < 0) return;
    final bytes = base64Decode(dataUrl.substring(comma + 1));
    if (!_controller.isClosed) _controller.add(bytes);
  }

  @override
  Widget preview() => HtmlElementView(viewType: _viewType);

  @override
  void stop() {
    _timer?.cancel();
    _timer = null;
    final stream = _stream;
    if (stream != null) {
      final tracks = stream.getTracks().toDart;
      for (final track in tracks) {
        track.stop();
      }
      _stream = null;
    }
    _video?.srcObject = null;
    if (!_controller.isClosed) _controller.close();
  }
}

/// 스파이크 화면: 카메라 프리뷰 + 그 위 CustomPaint 오버레이(프레임마다 갱신되는 사각형 +
/// "받은 프레임 N장 · X KB · Y fps" 텍스트). 프레임이 실제로 흐르는지 눈으로 본다.
class CameraSpikeScreen extends StatefulWidget {
  const CameraSpikeScreen({super.key});

  @override
  State<CameraSpikeScreen> createState() => _CameraSpikeScreenState();
}

class _CameraSpikeScreenState extends State<CameraSpikeScreen> {
  final WebFrameSource _source = WebFrameSource();
  final ValueNotifier<_FrameStat> _stat =
      ValueNotifier<_FrameStat>(const _FrameStat.empty());

  StreamSubscription<Uint8List>? _sub;
  String? _error;
  bool _ready = false;

  // fps 측정: 최근 2초 창에 들어온 프레임 타임스탬프 개수 / 창 길이.
  final List<int> _recentMs = <int>[];

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    try {
      await _source.start();
      _sub = _source.frames().listen(_onFrame);
      if (mounted) setState(() => _ready = true);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  void _onFrame(Uint8List bytes) {
    final now = DateTime.now().millisecondsSinceEpoch;
    _recentMs.add(now);
    while (_recentMs.isNotEmpty && now - _recentMs.first > 2000) {
      _recentMs.removeAt(0);
    }
    final windowMs = _recentMs.length > 1 ? (now - _recentMs.first) : 0;
    final fps = windowMs > 0 ? (_recentMs.length - 1) * 1000 / windowMs : 0.0;

    final prev = _stat.value;
    _stat.value = _FrameStat(
      count: prev.count + 1,
      lastBytes: bytes.length,
      fps: fps,
    );
  }

  @override
  void dispose() {
    _sub?.cancel();
    _source.stop();
    _stat.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: _error != null
            ? _ErrorView(message: _error!)
            : !_ready
                ? const Center(
                    child: Text('카메라 여는 중…',
                        style: TextStyle(color: Colors.white70)),
                  )
                : Stack(
                    fit: StackFit.expand,
                    children: [
                      _source.preview(),
                      // 오버레이만 프레임마다 다시 그린다 — 프리뷰(HtmlElementView)는 안정 유지.
                      Positioned.fill(
                        child: ValueListenableBuilder<_FrameStat>(
                          valueListenable: _stat,
                          builder: (_, stat, __) => CustomPaint(
                            painter: _OverlayPainter(stat),
                          ),
                        ),
                      ),
                    ],
                  ),
      ),
    );
  }
}

@immutable
class _FrameStat {
  const _FrameStat({
    required this.count,
    required this.lastBytes,
    required this.fps,
  });
  const _FrameStat.empty()
      : count = 0,
        lastBytes = 0,
        fps = 0;

  final int count;
  final int lastBytes;
  final double fps;
}

/// 프리뷰 위에 그려지는 걸 증명하는 오버레이. 프레임 수에 따라 움직이는 사각형 +
/// 실시간 통계 텍스트. (좌표 주의: 여기 좌표는 **프리뷰 표시 크기** 기준이지 다운스케일
/// 프레임(480px) 기준이 아니다 — 서버 관절 좌표를 그릴 땐 프레임→프리뷰 스케일 변환 필요.)
class _OverlayPainter extends CustomPainter {
  _OverlayPainter(this.stat);
  final _FrameStat stat;

  @override
  void paint(Canvas canvas, Size size) {
    // 프레임 카운트로 위치가 도는 사각형 — 프레임이 실제로 흐르면 눈에 띄게 움직인다.
    final t = stat.count / 8.0;
    final cx = size.width / 2 + (size.width * 0.28) * math.cos(t);
    final cy = size.height / 2 + (size.height * 0.22) * math.sin(t);
    final box = Rect.fromCenter(center: Offset(cx, cy), width: 120, height: 120);

    final stroke = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4
      ..color = const Color(0xFF5EE0CE); // teal_bright — 검정/영상 위 잘 보인다
    canvas.drawRRect(
      RRect.fromRectAndRadius(box, const Radius.circular(12)),
      stroke,
    );

    final kb = (stat.lastBytes / 1024).toStringAsFixed(1);
    final fps = stat.fps.toStringAsFixed(1);
    final tp = TextPainter(
      text: TextSpan(
        text: '받은 프레임 ${stat.count}장  ·  $kb KB/장  ·  $fps fps',
        style: const TextStyle(
          color: Colors.white,
          fontSize: 16,
          fontWeight: FontWeight.w700,
          shadows: [Shadow(color: Colors.black, blurRadius: 4)],
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout(maxWidth: size.width - 32);
    tp.paint(canvas, const Offset(16, 16));
  }

  @override
  bool shouldRepaint(_OverlayPainter old) => old.stat.count != stat.count;
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message});
  final String message;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.videocam_off, color: Colors.white70, size: 48),
            const SizedBox(height: 16),
            const Text(
              '카메라를 쓸 수 없어요',
              style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.white54, fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}
