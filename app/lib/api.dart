import 'dart:convert';
import 'package:http/http.dart' as http;

/// 백엔드 API 클라이언트. 토큰은 메모리에만 보관 (DB 없음 — 앱 재시작 시 재로그인 필요).
class Api {
  Api._();
  static final Api instance = Api._();

  // 로컬 백엔드. Android 에뮬레이터에서 테스트 시 10.0.2.2로 교체.
  static const String baseUrl = 'http://localhost:8000';

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

  /// 프레임 한 장을 자세 판정에 넘긴다 → `{detected, keypoints, evaluation{form_score, verdict, checks[]}}`.
  ///
  /// 카메라가 붙기 전까지는 [placeholderFrame]을 쓴다. 백엔드의 StubPoseEstimator는
  /// 이미지 내용을 보지 않지만 **각도 계산과 판정은 실제 pose_eval이 수행**하므로,
  /// 여기서 받은 checks는 진짜 파이프라인 산출물이다. 카메라가 생기면 프레임만 갈아끼우면 된다.
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

  /// 1x1 투명 PNG. 카메라 프레임이 없을 때 자세 판정 파이프라인을 태우기 위한 자리표시자.
  /// 백엔드가 `imghdr`로 이미지 여부만 확인하므로 최소 PNG면 통과한다.
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
