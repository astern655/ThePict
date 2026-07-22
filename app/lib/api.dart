import 'dart:convert';
import 'package:http/http.dart' as http;

/// 백엔드 API 클라이언트. 토큰은 메모리에만 보관 (DB 없음 — 앱 재시작 시 재로그인 필요).
class Api {
  Api._();
  static final Api instance = Api._();

  /// 백엔드 주소. 기본은 로컬 웹 개발용이다.
  ///
  /// Android 에뮬레이터(호스트가 10.0.2.2)나 실기기에서는 빌드할 때 넘긴다:
  ///   flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
  /// 컴파일 타임 상수라 `dart:io` 없이 웹/모바일 모두에서 동작한다.
  static const String baseUrl =
      String.fromEnvironment('API_BASE_URL', defaultValue: 'http://localhost:8000');

  String? token;

  bool get isLoggedIn => token != null;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('$baseUrl$path').replace(queryParameters: query);

  dynamic _decode(http.Response res) {
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw ApiException(_friendlyMessage(res.statusCode), res.statusCode);
    }
    if (res.body.isEmpty) return null;
    return jsonDecode(utf8.decode(res.bodyBytes));
  }

  // 오류는 원인과 다음 행동을 사용자 언어로 (상태코드·내부 응답 노출 금지).
  static String _friendlyMessage(int status) {
    switch (status) {
      case 401:
        return '이메일 또는 비밀번호가 맞지 않아요. 다시 확인해 주세요.';
      case 409:
        return '이미 가입된 이메일이에요. 로그인으로 진행해 주세요.';
      case 400:
        return '입력한 내용을 처리할 수 없어요. 값을 확인해 주세요.';
      case 413:
        return '영상이 너무 커요. 한 세트 분량(100MB 이하)으로 다시 찍어 주세요.';
      case 503:
        return '자세 분석 기능이 지금 준비되지 않았어요. 잠시 후 다시 시도해 주세요.';
      default:
        return '서버와 연결하지 못했어요. 잠시 후 다시 시도해 주세요.';
    }
  }

  Future<void> register(String email, String password) async {
    final res = await http.post(_uri('/auth/register'),
        headers: _headers, body: jsonEncode({'email': email, 'password': password}));
    final data = _decode(res);
    token = data['token'] as String;
  }

  Future<void> login(String email, String password) async {
    final res = await http.post(_uri('/auth/login'),
        headers: _headers, body: jsonEncode({'email': email, 'password': password}));
    final data = _decode(res);
    token = data['token'] as String;
  }

  void logout() {
    token = null;
  }

  Future<Map<String, dynamic>> getProfile() async {
    final res = await http.get(_uri('/me/profile'), headers: _headers);
    return _decode(res) as Map<String, dynamic>;
  }

  Future<void> updateProfile(Map<String, dynamic> fields) async {
    final res = await http.put(_uri('/me/profile'), headers: _headers, body: jsonEncode(fields));
    _decode(res);
  }

  Future<void> deleteAccount() async {
    final res = await http.delete(_uri('/me'), headers: _headers);
    if (res.statusCode != 204 && (res.statusCode < 200 || res.statusCode >= 300)) {
      throw ApiException(_friendlyMessage(res.statusCode), res.statusCode);
    }
  }

  Future<List<dynamic>> getExercises() async {
    final res = await http.get(_uri('/exercises'), headers: _headers);
    return _decode(res) as List<dynamic>;
  }

  Future<Map<String, dynamic>> postSession({
    required String exerciseId,
    required DateTime startedAt,
    required List<Map<String, dynamic>> sets,
  }) async {
    final res = await http.post(
      _uri('/sessions'),
      headers: _headers,
      body: jsonEncode({
        'exercise_id': exerciseId,
        'started_at': startedAt.toIso8601String(),
        'sets': sets,
      }),
    );
    return _decode(res) as Map<String, dynamic>;
  }

  /// date 생략 시 전체 세션 반환 (백엔드가 이미 지원 — 클라이언트 집계용).
  Future<List<dynamic>> getSessions([String? date]) async {
    final res =
        await http.get(_uri('/sessions', date != null ? {'date': date} : null), headers: _headers);
    return _decode(res) as List<dynamic>;
  }

  Future<Map<String, dynamic>> getCalendar(String month) async {
    final res = await http.get(_uri('/calendar', {'month': month}), headers: _headers);
    return _decode(res) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getCompare(String exerciseId) async {
    final res = await http.get(_uri('/compare', {'exercise_id': exerciseId}), headers: _headers);
    return _decode(res) as Map<String, dynamic>;
  }

  /// 오늘의 운동 계획 — 세트/횟수/휴식초. 우선순위: 개인설정 > 점진증가 > 기본프리셋.
  /// [level] 생략 시 개인설정 또는 기본(beginner)을 따른다.
  Future<Map<String, dynamic>> getPlan(String exerciseId, {String? level}) async {
    final res = await http.get(
      _uri('/me/plan', {'exercise_id': exerciseId, if (level != null) 'level': level}),
      headers: _headers,
    );
    return _decode(res) as Map<String, dynamic>;
  }

  /// 운동별 개인 설정 목록.
  Future<List<dynamic>> getPrograms() async {
    final res = await http.get(_uri('/me/programs'), headers: _headers);
    return _decode(res) as List<dynamic>;
  }

  /// 운동별 개인 설정 저장. null인 필드는 프리셋/점진증가 값을 따른다.
  Future<Map<String, dynamic>> putProgram(
    String exerciseId, {
    String? level,
    int? sets,
    int? reps,
    int? restSec,
  }) async {
    final res = await http.put(
      _uri('/me/programs/$exerciseId'),
      headers: _headers,
      body: jsonEncode({
        'level': level,
        'sets': sets,
        'reps': reps,
        'rest_sec': restSec,
      }),
    );
    return _decode(res) as Map<String, dynamic>;
  }

  /// 세션 하나의 문장 분석 — good/bad/change/next/notes.
  Future<Map<String, dynamic>> getSessionAnalysis(String sessionId) async {
    final res = await http.get(_uri('/sessions/$sessionId/analysis'), headers: _headers);
    return _decode(res) as Map<String, dynamic>;
  }

  /// 그날의 세션 + 각 세션 분석을 한 번에 (캘린더 날짜 탭용, N+1 방지).
  Future<Map<String, dynamic>> getDayAnalysis(String date) async {
    final res = await http.get(_uri('/analysis', {'date': date}), headers: _headers);
    return _decode(res) as Map<String, dynamic>;
  }

  /// 프레임 한 장을 자세 판정에 넘긴다.
  /// → `{detected, estimator, measured, keypoints, evaluation{form_score, verdict, checks[]}}`
  ///
  /// **`measured`가 false면 좌표가 더미다.** 백엔드가 `POSE_ESTIMATOR=stub`으로 떠 있다는
  /// 뜻이며, 그 좌표로 계산한 checks는 이미지와 아무 관계가 없다. 각도 계산 자체는 진짜
  /// 코드가 돌지만 입력이 가짜라 결과도 가짜다 — 절대 세션에 저장하면 안 된다.
  /// 저장하면 분석이 지어낸 값으로 "엉덩이를 더 빼세요" 같은 교정 지시를 만들어 낸다.
  Future<Map<String, dynamic>> postPoseFrame({
    required String exerciseId,
    required List<int> frameBytes,
  }) async {
    final req = http.MultipartRequest('POST', _uri('/inference/pose'))
      ..fields['exercise_id'] = exerciseId
      ..files.add(http.MultipartFile.fromBytes('frame', frameBytes, filename: 'frame.png'));
    if (token != null) req.headers['Authorization'] = 'Bearer $token';
    final res = await http.Response.fromStream(await req.send());
    return _decode(res) as Map<String, dynamic>;
  }

  /// 운동 영상 한 편을 AI 엔진에 넘겨 실제 분석을 받는다.
  /// → `{report{rep_count, rep_verdicts[], issues[], summary[], ...}, set{reps, form_score, checks[]}}`
  ///
  /// [postPoseFrame]과 달리 여기는 **항상 실제 YOLO 엔진**이 돈다(stub 경로가 없다).
  /// 반환된 `set`은 그대로 [postSession]의 sets에 넣을 수 있다.
  ///
  /// 스쿼트는 **측면 촬영**만 받는다. 정면 영상이면 report의 `video_issues`에 경고가 붙는다.
  /// 분석은 영상 길이에 비례해 수 초~수십 초 걸리므로 호출부는 진행 표시를 띄워야 한다.
  Future<Map<String, dynamic>> postWorkoutVideo({
    required String exerciseId,
    required List<int> videoBytes,
    String filename = 'workout.mp4',
  }) async {
    final req = http.MultipartRequest('POST', _uri('/inference/video'))
      ..fields['exercise_id'] = exerciseId
      ..files.add(http.MultipartFile.fromBytes('video', videoBytes, filename: filename));
    if (token != null) req.headers['Authorization'] = 'Bearer $token';
    final res = await http.Response.fromStream(await req.send());
    return _decode(res) as Map<String, dynamic>;
  }

  /// 1x1 투명 PNG. 카메라 프레임이 없을 때 자세 판정 파이프라인을 태우기 위한 자리표시자.
  /// 백엔드는 매직 넘버로 이미지 여부만 확인하므로 최소 PNG면 통과한다.
  ///
  /// 실제 YOLO 추정기에서는 사람이 없어 `detected: false`가 나온다. 파이프라인이
  /// 살아 있는지 확인하는 용도이지, 자세 판정을 얻는 용도가 아니다.
  static final List<int> placeholderFrame = base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
  );
}

class ApiException implements Exception {
  final String message;
  final int? statusCode;
  ApiException(this.message, [this.statusCode]);
  @override
  String toString() => message;
}
