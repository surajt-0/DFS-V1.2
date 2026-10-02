from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Profile

User = get_user_model()


class ProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email")
    first_name = serializers.CharField(source="user.first_name", required=False, allow_blank=True)
    last_name = serializers.CharField(source="user.last_name", required=False, allow_blank=True)
    is_admin = serializers.BooleanField(source="is_admin_role", read_only=True)
    is_viewer = serializers.BooleanField(source="is_viewer_role", read_only=True)

    class Meta:
        model = Profile
        fields = [
            "username", "email", "first_name", "last_name",
            "role", "organization", "badge_id", "is_org_owner",
            "is_admin", "is_viewer", "created_at",
        ]
        read_only_fields = ["role", "is_org_owner", "created_at"]

    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", {})
        user = instance.user
        for field in ("email", "first_name", "last_name"):
            if field in user_data:
                setattr(user, field, user_data[field])
        user.save()
        return super().update(instance, validated_data)


class SignupSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password1 = serializers.CharField(write_only=True)
    password2 = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    organization = serializers.CharField(max_length=150)
    badge_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=Profile.Role.choices, required=False, default=Profile.Role.ADMIN)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("That username is already taken.")
        return value

    def validate(self, attrs):
        from django.contrib.auth.password_validation import validate_password

        if attrs["password1"] != attrs["password2"]:
            raise serializers.ValidationError({"password2": "Passwords don't match."})
        validate_password(attrs["password1"])
        return attrs

    def create(self, validated_data):
        from billing.access import free_plan
        from billing.models import Organization

        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password1"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
        )
        org = Organization.objects.create(
            name=validated_data["organization"] or f"{user.username}'s organization",
            owner=user,
            plan=free_plan(),
        )
        profile = user.profile
        profile.organization = validated_data["organization"]
        profile.badge_id = validated_data.get("badge_id", "")
        profile.role = validated_data.get("role", Profile.Role.ADMIN)
        profile.org = org
        profile.is_org_owner = True
        profile.save()
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
