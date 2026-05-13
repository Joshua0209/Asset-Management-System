import React, { useState, useEffect } from 'react';
import { Image, Skeleton } from 'antd';
import type { ImageProps } from 'antd';
import { apiClient } from '@/api';

interface AuthImageProps extends Omit<ImageProps, 'src'> {
  imageId: string;
  fallbackSrc?: string;
}

const AuthImage: React.FC<AuthImageProps> = ({ imageId, fallbackSrc, ...props }) => {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    let url = '';

    const fetchImage = async () => {
      setLoading(true);
      setError(false);
      try {
        // Fetch the image as a blob using the authenticated apiClient
        const response = await apiClient.get(`/images/${imageId}`, {
          responseType: 'blob',
        });

        if (!active) return;

        url = URL.createObjectURL(response.data as Blob);
        setObjectUrl(url);
      } catch (err) {
        if (!active) return;
        console.error('Failed to load image:', err);
        setError(true);
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void fetchImage();

    return () => {
      active = false;
      if (url) {
        URL.revokeObjectURL(url);
      }
    };
  }, [imageId]);

  if (loading) {
    return <Skeleton.Image active style={{ width: props.width, height: props.height }} />;
  }

  if (error || !objectUrl) {
    return <Image src={fallbackSrc} {...props} />;
  }

  return <Image src={objectUrl} {...props} />;
};

export default AuthImage;
