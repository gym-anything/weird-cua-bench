"""Gym-Anything worker with the benchmark's fixed input/receipt endpoint."""


def install_routes(worker):
    from flask import jsonify, request
    from weird_captcha_gym.scheduled_input import execute_input, prepare_input, close_input

    if "weird_input" in worker.app.view_functions:
        return

    def input_action(env_id):
        try:
            env = worker.env_manager.get_environment(env_id)
            data = request.get_json()
            if not isinstance(data, dict) or set(data) - {"actions", "execute_at_s", "request_id"}:
                raise ValueError("invalid input request")
            if not isinstance(data.get("request_id"), str):
                raise ValueError("request_id is required")
            return jsonify(execute_input(env, data["actions"], data.get("execute_at_s"), request_id=data["request_id"]))
        except (ValueError, KeyError) as error:
            return jsonify({"error": str(error)}), 400
        except Exception as error:
            return jsonify({"error": str(error)}), 500

    worker.app.add_url_rule("/envs/<env_id>/weird/input", "weird_input", input_action, methods=["POST"])

    def input_ready(env_id):
        try:
            return jsonify(prepare_input(worker.env_manager.get_environment(env_id)))
        except Exception as error:
            return jsonify({"error": str(error)}), 500

    worker.app.add_url_rule("/envs/<env_id>/weird/input-ready", "weird_input_ready", input_ready, methods=["POST"])

    def input_close(env_id):
        try:
            close_input(worker.env_manager.get_environment(env_id))
            return jsonify({"closed": True})
        except Exception as error:
            return jsonify({"error": str(error)}), 500

    worker.app.add_url_rule("/envs/<env_id>/weird/input-close", "weird_input_close", input_close, methods=["POST"])


def main():
    from gym_anything.remote import worker
    install_routes(worker)
    worker.main()


if __name__ == "__main__":
    main()
