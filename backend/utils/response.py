from flask import jsonify


def success(data=None, message='操作成功'):
    resp = {'code': 200, 'message': message}
    if data is not None:
        resp['data'] = data
    return jsonify(resp)


def created(data=None, message='创建成功'):
    resp = {'code': 201, 'message': message}
    if data is not None:
        resp['data'] = data
    return jsonify(resp), 201


def bad_request(message='请求参数错误'):
    return jsonify({'code': 400, 'message': message}), 400


def unauthorized(message='未授权'):
    return jsonify({'code': 401, 'message': message}), 401


def not_found(message='资源不存在'):
    return jsonify({'code': 404, 'message': message}), 404


def conflict(message='资源已存在'):
    return jsonify({'code': 409, 'message': message}), 409
